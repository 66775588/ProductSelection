# src/dianshang/server/app.py
"""FastAPI 服务：路由 + 静态挂载 + 启动恢复/卡死清理。"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator

from dianshang.config import settings
from dianshang.memory import long_term as mem
from dianshang.server import config_store, jobs, paths, runner

STATIC_DIR = Path(__file__).parent / "static"
PLATFORMS = {"pdd", "taobao", "tmall", "jd"}
STALE_MINUTES = 30


class ResearchRequest(BaseModel):
    category: str
    platform: str = "pdd"
    overrides: dict[str, Any] | None = None

    @field_validator("platform")
    @classmethod
    def _check_platform(cls, v: str) -> str:
        if v not in PLATFORMS:
            raise ValueError(f"platform 必须是 {PLATFORMS} 之一")
        return v


def _err(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _cleanup_stale() -> None:
    for jid in mem.stale_jobs(STALE_MINUTES):
        mem.release_job(jid)
        st = jobs.job_store.get(jid)
        if st:
            jobs.job_store.update(jid, status="error", error="任务超时被清理")


def _restore_inflight() -> None:
    """启动时恢复未超时的 running 任务为 stale 标记。"""
    cur = mem.get_running_job()
    if not cur:
        return
    if mem.stale_jobs(STALE_MINUTES):
        _cleanup_stale()
        return
    jid = cur["job_id"]
    completed = mem.load_progress(jid)
    jobs.job_store.set(jid, jobs.JobStatus(
        job_id=jid, status="running", stale=True,
        completed_nodes=completed,
        current_node=completed[-1] if completed else None,
        error="服务重启，任务可能已中断，可取消重跑",
    ))


def _stale_loop() -> None:
    while True:
        time.sleep(300)
        try:
            _cleanup_stale()
        except Exception:  # noqa: BLE001
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="选品调研 Agent")
    mem.init_db()
    _restore_inflight()
    threading.Thread(target=_stale_loop, daemon=True).start()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/research")
    def research(req: ResearchRequest):
        job_id = uuid.uuid4().hex[:12]
        if not mem.claim_job(job_id, req.category, req.platform):
            return _err("job_running", "已有任务运行中，请先完成或取消", 409)
        jobs.job_store.set(job_id, jobs.JobStatus(job_id=job_id, status="queued"))
        t = threading.Thread(
            target=runner.run_job,
            args=(job_id, req.category, req.platform, req.overrides),
            daemon=True,
        )
        t.start()
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        st = jobs.job_store.get(job_id)
        if not st:
            return _err("not_found", "任务不存在", 404)
        return {
            "job_id": st.job_id, "status": st.status,
            "current_node": st.current_node, "completed_nodes": st.completed_nodes,
            "result": st.result, "error": st.error,
            "errors": st.errors, "warnings": st.warnings, "stale": st.stale,
        }

    @app.delete("/api/jobs/{job_id}")
    def cancel_job(job_id: str):
        mem.release_job(job_id)
        jobs.job_store.update(job_id, status="cancelled")
        return {"ok": True}

    @app.get("/api/history")
    def history(limit: int = 50, offset: int = 0):
        if limit < 1 or limit > 200:
            return _err("bad_param", "limit 须在 1–200", 400)
        items = mem.list_history(limit=limit, offset=offset)
        # 总数：再查一次未分页计数
        with mem._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM selections").fetchone()[0]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/history/{rid}")
    def history_detail(rid: int):
        with mem._connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            row = conn.execute("SELECT * FROM selections WHERE id=?", (rid,)).fetchone()
        if not row:
            return _err("not_found", "记录不存在", 404)
        import json
        d = dict(row)
        d["report_paths"] = json.loads(d.get("report_paths") or "{}")
        d["state_json"] = json.loads(d.get("state_json") or "{}")
        return d

    @app.get("/api/reports/{filename:path}")
    def download_report(filename: str):
        safe = paths.sanitize_report_path(filename)
        if safe is None or not safe.exists():
            return _err("bad_path", "非法或不存在 的报告文件", 400)
        return FileResponse(str(safe), filename=safe.name)

    @app.get("/api/config")
    def get_config():
        return config_store.current_config()

    @app.put("/api/config")
    def put_config(payload: dict[str, Any]):
        errs = config_store.validate_overrides(payload)
        if errs:
            return _err("invalid_config", "; ".join(errs), 400)
        try:
            merged = config_store.save_overrides(payload)
        except ValueError as e:
            return _err("invalid_config", str(e), 400)
        return merged

    # 静态前端
    from fastapi.staticfiles import StaticFiles
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app


def main():
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
