"""LangGraph 节点实现：9 个节点，各读写 AgentState。

节点间通过 state 传递数据，单个节点失败不阻断流程——记录到 state.errors 并用默认值兜底。
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter
from typing import Any

from dianshang.agent.prompts import SELLING_POINT_PROMPT, SYSTEM_PROMPT, format_prompt
from dianshang.agent.state import AgentState
from dianshang.analysis import pain_points as pp
from dianshang.analysis.llm import llm_client
from dianshang.analysis.profit import calculate_profit
from dianshang.analysis.scoring import compute_scores
from dianshang.config import settings
from dianshang.datasources.base import CompositeDataSource
from dianshang.datasources.models import Dataset
from dianshang.risk.checker import check_risks
from dianshang.utils.cleaner import clean_dataset, mark_missing

logger = logging.getLogger(__name__)


def task_decompose(state: AgentState) -> AgentState:
    """节点1：解析输入，拆解数据需求。"""
    category = state.get("category", "").strip()
    platform = state.get("platform", "pdd").strip()
    if not category:
        raise ValueError("必须提供目标品类（category）")
    state["category"] = category
    state["platform"] = platform
    state["task_plan"] = {
        "data_needs": ["market", "competitors", "reviews", "supply"],
        "steps": ["fetch", "clean", "analyze", "profit", "risk", "score", "report", "memory"],
    }
    state.setdefault("errors", [])
    state.setdefault("warnings", [])
    logger.info("任务拆解完成：品类=%s 平台=%s", category, platform)
    return state


def data_fetch(state: AgentState) -> AgentState:
    """节点2：并行抓取四类数据，失败回退 Mock。"""
    try:
        ds = CompositeDataSource()
        dataset = ds.fetch(state["category"], state["platform"])
        state["raw_dataset"] = dataset
        state["data_provenance"] = dataset.source_notes
    except Exception as exc:  # noqa: BLE001
        logger.exception("数据抓取整体失败")
        state.setdefault("errors", []).append(f"数据抓取失败: {exc}")
        state["raw_dataset"] = Dataset()
    return state


def data_clean(state: AgentState) -> AgentState:
    """节点3：清洗去重、异常值校验、缺失标记。"""
    dataset: Dataset = state.get("raw_dataset", Dataset())
    cleaned = clean_dataset(dataset)
    state["cleaned_dataset"] = cleaned
    state["missing"] = mark_missing(cleaned)
    if state["missing"]:
        state.setdefault("warnings", []).append(
            "存在数据不足项: " + ", ".join(state["missing"].keys())
        )
    return state


def analyze(state: AgentState) -> AgentState:
    """节点4：痛点聚类 + 卖点拆解 + 竞品结构分析。"""
    ds: Dataset = state.get("cleaned_dataset", Dataset())
    category = state["category"]

    # 痛点聚类
    try:
        state["pain_points"] = pp.cluster_pain_points(category, ds.reviews)
    except Exception as exc:  # noqa: BLE001
        logger.warning("痛点分析失败: %s", exc)
        state["pain_points"] = []
        state.setdefault("errors", []).append(f"痛点分析失败: {exc}")

    # 竞品结构分析（确定性统计）
    comps = ds.competitors
    if comps:
        sales = [c.sales for c in comps]
        prices = [c.price for c in comps]
        total_sales = sum(sales) or 1
        state["competitor_analysis"] = {
            "count": len(comps),
            "avg_price": round(statistics.mean(prices), 2),
            "median_price": round(statistics.median(prices), 2),
            "avg_sales": round(statistics.mean(sales)),
            "top3_monopoly_rate": round(sum(sorted(sales, reverse=True)[:3]) / total_sales, 3),
            "price_band": [round(min(prices), 1), round(max(prices), 1)],
        }
    else:
        state["competitor_analysis"] = {}

    # 卖点拆解 + 差异化方向（LLM，降级为统计）
    state["selling_points"], state["differentiation"] = _selling_and_diff(category, comps, state["pain_points"])
    return state


def _selling_and_diff(category, comps, pain_points):
    if llm_client.available and comps:
        source = "真实爬取" if comps[0].source.value == "real_scrape" else "模拟数据"
        comp_text = "\n".join(
            f"- {c.title} 售价{c.price}元 月销{c.sales} 店铺等级{c.shop_level} 标签{','.join(c.tags)}"
            for c in comps[:15]
        )
        prompt = format_prompt(SELLING_POINT_PROMPT, category=category, competitors=comp_text, source=source)
        data = llm_client.chat_json(SYSTEM_PROMPT, prompt)
        if data:
            diff = data.get("differentiation", [])[:3]
            if not diff:
                diff = _diff_from_pain(pain_points)
            return data.get("selling_points", [])[:10], diff
    # 降级：标签词频 + 痛点反向
    tag_counter: Counter[str] = Counter()
    for c in comps:
        tag_counter.update(c.tags)
    selling = [{"point": t, "frequency": n} for t, n in tag_counter.most_common(10)]
    return selling, _diff_from_pain(pain_points)


def _diff_from_pain(pain_points) -> list[str]:
    """无 LLM 时：差异化方向 = 反向痛点 TOP3。"""
    if not pain_points:
        return ["待补充：需更多评论数据支撑差异化方向"]
    return [f"解决「{p['keyword']}」痛点，作为核心差异化卖点" for p in pain_points[:3]]


def profit_calc(state: AgentState) -> AgentState:
    """节点5：成本利润测算。"""
    ds: Dataset = state.get("cleaned_dataset", Dataset())
    try:
        state["profit"] = calculate_profit(ds.competitors, ds.supply)
        if state["profit"].get("below_threshold"):
            state.setdefault("warnings", []).append(
                f"毛利率 {state['profit']['gross_margin']}% 低于阈值 {state['profit']['threshold']}%"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("利润测算失败: %s", exc)
        state["profit"] = None
        state.setdefault("errors", []).append(f"利润测算失败: {exc}")
    return state


def risk_check(state: AgentState) -> AgentState:
    """节点6：风险排查。"""
    ds: Dataset = state.get("cleaned_dataset", Dataset())
    supply_dicts = [s.model_dump() for s in ds.supply]
    try:
        items, red_line = check_risks(state["category"], state.get("pain_points", []), supply_dicts)
        state["risk_items"] = items
        state["red_line_hit"] = red_line
        if red_line:
            state.setdefault("warnings", []).append("命中红线规则，将直接判定不推荐")
    except Exception as exc:  # noqa: BLE001
        logger.warning("风险排查失败: %s", exc)
        state["risk_items"] = []
        state["red_line_hit"] = False
        state.setdefault("errors", []).append(f"风险排查失败: {exc}")
    return state


def score(state: AgentState) -> AgentState:
    """节点7：五维加权打分。"""
    ds: Dataset = state.get("cleaned_dataset", Dataset())
    market = ds.market.model_dump() if ds.market else None
    comp_dicts = [c.model_dump() for c in ds.competitors]
    result = compute_scores(
        market=market,
        competitors=comp_dicts,
        profit=state.get("profit"),
        pain_points=state.get("pain_points", []),
        risk_items=state.get("risk_items", []),
        red_line_hit=state.get("red_line_hit", False),
    )
    state["scores"] = result["dimensions"]
    state["total_score"] = result["total_score"]
    state["recommendation"] = result["recommendation"]
    state["recommendation_reason"] = result["reason"]
    return state


def report(state: AgentState) -> AgentState:
    """节点8：生成报告。"""
    from dianshang.report.generator import generate_reports

    try:
        state["report_paths"] = generate_reports(state)
    except Exception as exc:  # noqa: BLE001
        logger.exception("报告生成失败")
        state.setdefault("errors", []).append(f"报告生成失败: {exc}")
        state["report_paths"] = {}
    return state


def memory_save(state: AgentState) -> AgentState:
    """节点9：写入长期记忆库。"""
    from dianshang.memory.long_term import save_selection

    try:
        save_selection(state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("记忆写入失败: %s", exc)
        state.setdefault("errors", []).append(f"记忆写入失败: {exc}")
    return state
