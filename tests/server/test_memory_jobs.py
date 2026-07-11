# tests/server/test_memory_jobs.py
from datetime import datetime, timedelta

from dianshang.memory import long_term as mem


def test_claim_job_atomic_and_release(tmp_path, monkeypatch):
    db = tmp_path / "m.db"
    monkeypatch.setattr(mem.settings.paths, "memory_db", db)
    mem.init_db()

    assert mem.claim_job("j1", "保温杯", "pdd") is True
    # 同一 job_id 再抢 / 第二个 running job 都应失败
    assert mem.claim_job("j1", "保温杯", "pdd") is False
    assert mem.claim_job("j2", "瑜伽垫", "taobao") is False

    assert mem.get_running_job()["job_id"] == "j1"
    mem.release_job("j1")
    assert mem.get_running_job() is None
    # 释放后可新建
    assert mem.claim_job("j2", "瑜伽垫", "taobao") is True


def test_progress_append_and_load(tmp_path, monkeypatch):
    db = tmp_path / "m.db"
    monkeypatch.setattr(mem.settings.paths, "memory_db", db)
    mem.init_db()
    mem.claim_job("j1", "保温杯", "pdd")
    mem.append_progress("j1", "task_decompose")
    mem.append_progress("j1", "data_fetch")
    # 幂等：重复写同一 node 不重复
    mem.append_progress("j1", "task_decompose")
    assert mem.load_progress("j1") == ["task_decompose", "data_fetch"]


def test_stale_jobs(tmp_path, monkeypatch):
    db = tmp_path / "m.db"
    monkeypatch.setattr(mem.settings.paths, "memory_db", db)
    mem.init_db()
    mem.claim_job("old", "保温杯", "pdd")
    # 篡改 started_at 为 60 分钟前
    old = (datetime.now() - timedelta(minutes=60)).isoformat()
    with mem._connect() as conn:
        conn.execute("UPDATE running_jobs SET started_at=? WHERE job_id=?", (old, "old"))
        conn.commit()
    assert mem.stale_jobs(30) == ["old"]
