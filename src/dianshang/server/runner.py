# src/dianshang/server/runner.py
"""流式跑图：LangGraph stream_mode=updates 驱动 9 节点进度。"""
from __future__ import annotations

import logging
from typing import Any

from dianshang.agent.graph import selection_graph
from dianshang.agent.state import AgentState
from dianshang.memory import long_term as mem
from dianshang.server import jobs
from dianshang.server.config_store import apply_overrides

logger = logging.getLogger(__name__)

NODE_LABELS: dict[str, str] = {
    "task_decompose": "任务拆解",
    "data_fetch": "数据抓取",
    "data_clean": "数据清洗",
    "analyze": "痛点分析",
    "profit_calc": "利润测算",
    "risk_check": "风险排查",
    "score": "综合评分",
    "report": "报告生成",
    "memory_save": "记忆存储",
}

NODE_ORDER = list(NODE_LABELS.keys())


def build_result(state: AgentState) -> dict[str, Any]:
    profit = state.get("profit") or {}
    # 竞品 TOP20 → 序列化为前端可渲染的结构
    raw_competitors = state.get("competitors") or []
    competitors = []
    for c in raw_competitors:
        competitors.append({
            "rank": getattr(c, "rank", 0),
            "title": getattr(c, "title", ""),
            "price": getattr(c, "price", 0),
            "sales": getattr(c, "sales", 0),
            "shop_name": getattr(c, "shop_name", ""),
            "url": getattr(c, "url", ""),
        })
    return {
        "category": state.get("category", ""),
        "platform": state.get("platform", ""),
        "recommendation": state.get("recommendation", ""),
        "recommendation_reason": state.get("recommendation_reason", ""),
        "total_score": state.get("total_score", 0),
        "scores": state.get("scores", {}),
        "profit": profit,
        "competitors": competitors,
        "pain_points": (state.get("pain_points") or [])[:5],
        "risk_items": state.get("risk_items", []),
        "red_line_hit": bool(state.get("red_line_hit", False)),
        "report_paths": state.get("report_paths", {}),
        "data_provenance": state.get("data_provenance", {}),
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", []),
    }


def run_job(job_id: str, category: str, platform: str = "pdd",
            overrides: dict[str, Any] | None = None) -> None:
    if overrides:
        apply_overrides(overrides)
    jobs.job_store.update(job_id, status="running", current_node=NODE_ORDER[0])
    initial: AgentState = {"category": category, "platform": platform}
    accumulated: dict[str, Any] = dict(initial)
    try:
        for chunk in selection_graph.stream(initial, stream_mode="updates"):
            for node_name, update in chunk.items():
                if node_name not in NODE_LABELS:
                    continue
                if isinstance(update, dict):
                    accumulated.update(update)
                st = jobs.job_store.get(job_id)
                completed = (st.completed_nodes if st else []) + [node_name]
                jobs.job_store.update(
                    job_id,
                    current_node=node_name,
                    completed_nodes=completed,
                )
                mem.append_progress(job_id, node_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("任务执行失败 job=%s", job_id)
        jobs.job_store.update(job_id, status="error", error=str(exc))
        mem.release_job(job_id)
        return

    result = build_result(accumulated)  # type: ignore[arg-type]
    jobs.job_store.update(
        job_id,
        status="done",
        result=result,
        errors=accumulated.get("errors", []),
        warnings=accumulated.get("warnings", []),
    )
    mem.release_job(job_id)
