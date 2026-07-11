"""长期记忆库：SQLite 存储历史选品结果 + 后续真实销量反馈。

供后续迭代：用真实销量反馈校准评分权重与提示词。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from dianshang.agent.state import AgentState
from dianshang.config import settings

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(settings.paths.memory_db)


def init_db() -> None:
    """建表（幂等）。"""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                platform TEXT,
                recommendation TEXT,
                total_score REAL,
                gross_margin REAL,
                red_line_hit INTEGER,
                created_at TEXT NOT NULL,
                report_paths TEXT,
                state_json TEXT,
                -- 后续真实销量反馈（手工或系统回传）
                actual_sales INTEGER,
                feedback_note TEXT,
                feedback_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS running_jobs (
                job_id     TEXT PRIMARY KEY,
                category   TEXT NOT NULL,
                platform   TEXT,
                started_at TEXT NOT NULL,
                status     TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_progress (
                job_id       TEXT NOT NULL,
                node_key     TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (job_id, node_key)
            )
            """
        )
        conn.commit()


def save_selection(state: AgentState) -> int:
    """保存一次选品结果，返回记录 id。"""
    init_db()
    profit = state.get("profit") or {}
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO selections
                (category, platform, recommendation, total_score, gross_margin,
                 red_line_hit, created_at, report_paths, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.get("category", ""),
                state.get("platform", ""),
                state.get("recommendation", ""),
                state.get("total_score", 0),
                profit.get("gross_margin"),
                int(state.get("red_line_hit", False)),
                datetime.now().isoformat(),
                json.dumps(state.get("report_paths", {}), ensure_ascii=False),
                json.dumps(
                    {
                        "scores": state.get("scores", {}),
                        "pain_points": state.get("pain_points", [])[:5],
                        "risk_items": state.get("risk_items", []),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
        rid = cur.lastrowid
        logger.info("选品结果已存入记忆库 id=%s", rid)
        return rid


def add_feedback(record_id: int, actual_sales: int, note: str = "") -> None:
    """回传真实销量反馈，用于后续模型迭代。"""
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE selections SET actual_sales=?, feedback_note=?, feedback_at=? WHERE id=?",
            (actual_sales, note, datetime.now().isoformat(), record_id),
        )
        conn.commit()


def list_history(limit: int = 50) -> list[dict[str, Any]]:
    """查询历史选品记录。"""
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, category, platform, recommendation, total_score, gross_margin, "
            "actual_sales, created_at FROM selections ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def claim_job(job_id: str, category: str, platform: str) -> bool:
    """原子抢占单任务锁。已有 running 任务则失败。"""
    init_db()
    with _connect() as conn:
        if conn.execute(
            "SELECT 1 FROM running_jobs WHERE status='running'"
        ).fetchone():
            return False
        try:
            conn.execute(
                "INSERT INTO running_jobs (job_id, category, platform, started_at, status) "
                "VALUES (?, ?, ?, ?, 'running')",
                (job_id, category, platform, datetime.now().isoformat()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_running_job() -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT job_id, category, platform, started_at FROM running_jobs WHERE status='running'"
        ).fetchone()
        return dict(row) if row else None


def release_job(job_id: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM running_jobs WHERE job_id=?", (job_id,))
        conn.execute("DELETE FROM job_progress WHERE job_id=?", (job_id,))
        conn.commit()


def stale_jobs(older_than_minutes: int = 30) -> list[str]:
    init_db()
    cutoff = (datetime.now() - timedelta(minutes=older_than_minutes)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT job_id FROM running_jobs WHERE status='running' AND started_at < ?",
            (cutoff,),
        ).fetchall()
        return [r[0] for r in rows]


def append_progress(job_id: str, node_key: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO job_progress (job_id, node_key, completed_at) VALUES (?, ?, ?)",
            (job_id, node_key, datetime.now().isoformat()),
        )
        conn.commit()


def load_progress(job_id: str) -> list[str]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT node_key FROM job_progress WHERE job_id=? ORDER BY rowid", (job_id,)
        ).fetchall()
        return [r[0] for r in rows]
