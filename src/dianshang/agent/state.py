"""Agent 全流程共享状态（LangGraph State）。

所有节点读写此状态，避免长参数列表。使用 TypedDict 以兼容 LangGraph 的 reducer。
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from dianshang.datasources.models import Dataset


class AgentState(TypedDict, total=False):
    # ---- 输入 ----
    category: str
    platform: str

    # ---- 任务拆解 ----
    task_plan: dict[str, Any]  # 数据需求清单 + 各步骤状态

    # ---- 数据 ----
    raw_dataset: Dataset
    cleaned_dataset: Dataset
    missing: dict[str, str]  # 缺失项标注（数据不足）

    # ---- 分析 ----
    pain_points: list[dict[str, Any]]  # TOP10 痛点 [{keyword, frequency, severity, sample}]
    selling_points: list[dict[str, Any]]  # 竞品卖点拆解
    competitor_analysis: dict[str, Any]  # 头部垄断率/均价/销量分布
    differentiation: list[str]  # 差异化切入方向 TOP3

    # ---- 利润 ----
    profit: dict[str, Any]  # 成本明细/毛利率/回本周期/盈亏平衡

    # ---- 风险 ----
    risk_items: list[dict[str, Any]]  # 风险清单 [{type, level, desc, mitigation}]
    red_line_hit: bool  # 命中红线（禁售/侵权高危）→ 直接不推荐

    # ---- 评分 ----
    scores: dict[str, float]  # 五维分数
    total_score: float
    recommendation: str  # 强烈推荐/可尝试/谨慎进入/不推荐
    recommendation_reason: str

    # ---- 报告 ----
    report_paths: dict[str, str]  # {md, xlsx, docx}
    data_provenance: dict[str, str]  # 各类数据来源（真实/模拟）

    # ---- 元信息 ----
    errors: list[str]
    warnings: list[str]
