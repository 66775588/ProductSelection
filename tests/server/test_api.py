# tests/server/test_api.py
import os
os.environ["FORCE_MOCK"] = "true"

import time

from fastapi.testclient import TestClient
from dianshang.server import app as appmod, jobs, runner
from dianshang.memory import long_term as mem


def client():
    return TestClient(appmod.create_app())


def test_research_poll_done_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    c = client()
    r = c.post("/api/research", json={"category": "保温杯", "platform": "pdd",
                                       "overrides": {"crawl": {"force_mock": True}}})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    st = c.get(f"/api/jobs/{job_id}").json()
    for _ in range(120):  # 最多等 ~120s
        st = c.get(f"/api/jobs/{job_id}").json()
        if st["status"] in ("done", "error"):
            break
        time.sleep(1)
    assert st["status"] == "done"
    assert len(st["completed_nodes"]) == 9
    assert "recommendation" in st["result"]


def test_concurrent_research_409(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    mem.claim_job("hold", "x", "pdd")  # 占住锁
    c = client()
    r = c.post("/api/research", json={"category": "保温杯", "platform": "pdd"})
    assert r.status_code == 409
    mem.release_job("hold")


def test_cancel_releases_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    mem.claim_job("c1", "x", "pdd")
    jobs.job_store.set("c1", jobs.JobStatus(job_id="c1", status="running"))
    c = client()
    r = c.delete("/api/jobs/c1")
    assert r.status_code == 200
    assert mem.get_running_job() is None


def test_path_traversal_rejected():
    c = client()
    for bad in ["../../etc/passwd", "/etc/passwd", "..\\secret"]:
        r = c.get(f"/api/reports/{bad}")
        # 400 = handler rejected; 404 = httpx normalised ".." out of the
        # route prefix before it reached the app (also a safe rejection).
        assert r.status_code in (400, 404)


def test_config_get_put_roundtrip():
    c = client()
    r = c.get("/api/config")
    assert r.status_code == 200
    cfg = r.json()
    r2 = c.put("/api/config", json={"crawl": {"force_mock": True}})
    assert r2.status_code == 200
    assert c.get("/api/config").json()["crawl"]["force_mock"] is True


def test_config_rejects_bad_weights():
    c = client()
    r = c.put("/api/config", json={"scoring_weights": {"market_potential": 0.9,
          "competition": 0.2, "profit": 0.2, "pain_points": 0.1, "risk": 0.1}})
    assert r.status_code == 400


def test_history_pagination_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    for i in range(3):
        mem.save_selection({"category": f"c{i}", "platform": "pdd", "recommendation": "可尝试",
                            "total_score": 70, "profit": {"gross_margin": 40},
                            "red_line_hit": False, "report_paths": {}, "scores": {},
                            "pain_points": [], "risk_items": []})
    c = client()
    r = c.get("/api/history?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3


def test_history_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    rid = mem.save_selection({"category": "c", "platform": "pdd", "recommendation": "可尝试",
                              "total_score": 70, "profit": {"gross_margin": 40},
                              "red_line_hit": False, "report_paths": {"md": "c.md"},
                              "scores": {"market_potential": 80}, "pain_points": [],
                              "risk_items": []})
    c = client()
    r = c.get(f"/api/history/{rid}")
    assert r.status_code == 200
    assert r.json()["category"] == "c"


def test_stale_job_cleanup_on_startup(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    mem.claim_job("old", "x", "pdd")
    old = (datetime.now() - timedelta(minutes=60)).isoformat()
    with mem._connect() as conn:
        conn.execute("UPDATE running_jobs SET started_at=? WHERE job_id=?", (old, "old"))
        conn.commit()
    assert mem.get_running_job() is not None
    client()  # create_app 触发启动清理
    assert mem.get_running_job() is None


def test_invalid_platform_rejected():
    c = client()
    r = c.post("/api/research", json={"category": "x", "platform": "amazon"})
    assert r.status_code == 422  # enum 校验
