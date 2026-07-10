"""报告生成主入口：聚合各节点结果 → Markdown / Excel / Word。

输出对应设计文档第六节「选品调研报告框架」7 个部分。
所有模拟数据在报告中加「（模拟）」标注。
"""
from __future__ import annotations

import logging
from datetime import datetime

from jinja2 import Template

from dianshang.agent.state import AgentState
from dianshang.config import settings
from dianshang.datasources.models import Dataset
from dianshang.report.exporters import export_excel, export_word
from dianshang.report.templates import MARKDOWN_TEMPLATE

logger = logging.getLogger(__name__)


def _build_context(state: AgentState) -> dict:
    ds: Dataset = state.get("cleaned_dataset", Dataset())
    provenance = state.get("data_provenance", {})
    profit = state.get("profit") or {}
    scores = state.get("scores", {})
    ca = state.get("competitor_analysis", {})

    # 核心优势 / 核心风险 摘要
    core_strengths = _core_strengths(state, ca, profit)
    core_risks = [r["desc"] for r in state.get("risk_items", [])[:3]] or ["无明显高危风险"]

    # 落地建议
    landing = _landing_suggestions(ds, profit, state.get("differentiation", []))

    return {
        "category": state.get("category", ""),
        "platform": state.get("platform", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "recommendation": state.get("recommendation", ""),
        "total_score": state.get("total_score", 0),
        "reason": state.get("recommendation_reason", ""),
        "scores": scores,
        "core_strengths": core_strengths,
        "core_risks": core_risks,
        "market": ds.market.model_dump() if ds.market else None,
        "competitors": [c.model_dump() for c in ds.competitors[:10]],
        "competitor_analysis": ca,
        "pain_points": state.get("pain_points", []),
        "differentiation": state.get("differentiation", []),
        "selling_points": state.get("selling_points", []),
        "profit": profit,
        "risk_items": state.get("risk_items", []),
        "landing": landing,
        "provenance": provenance,
        "missing": state.get("missing", {}),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
        "red_line_hit": state.get("red_line_hit", False),
    }


def _core_strengths(state: AgentState, ca: dict, profit: dict) -> list[str]:
    strengths = []
    market = state.get("cleaned_dataset", Dataset()).market
    if market and market.market_type == "蓝海":
        strengths.append("供需比高，属蓝海品类，竞争空白度大")
    if profit and profit.get("gross_margin", 0) >= profit.get("threshold", 30):
        strengths.append(f"毛利率 {profit['gross_margin']}%，盈利空间达标")
    if state.get("pain_points"):
        strengths.append(f"用户痛点明确（{len(state['pain_points'])} 项），差异化机会充足")
    if ca and ca.get("top3_monopoly_rate", 1) < 0.4:
        strengths.append("头部垄断率低，新店有切入空间")
    return strengths or ["数据不足以判断核心优势"]


def _landing_suggestions(ds: Dataset, profit: dict, differentiation: list[str]) -> dict:
    prices = [c.price for c in ds.competitors] or []
    price_band = f"{round(min(prices),1)}~{round(max(prices),1)}元" if prices else "数据不足"
    return {
        "price_band": price_band,
        "target_price": profit.get("selling_price", "数据不足"),
        "core_selling_points": differentiation[:3],
        "first_skus": _first_skus(ds),
    }


def _first_skus(ds: Dataset) -> list[str]:
    """从竞品标签归纳首发 SKU 配置建议。"""
    from collections import Counter

    tag_counter: Counter[str] = Counter()
    for c in ds.competitors:
        tag_counter.update(c.tags)
    top_tags = [t for t, _ in tag_counter.most_common(3)]
    if not top_tags:
        return ["数据不足，建议补充竞品 SKU 结构"]
    return [f"{tag}款（覆盖主流需求）" for tag in top_tags]


def generate_reports(state: AgentState) -> dict[str, str]:
    """生成 Markdown + Excel + Word 报告，返回路径字典。"""
    ctx = _build_context(state)
    category = ctx["category"] or "选品"
    # 文件名安全化
    safe = "".join(c for c in category if c.isalnum() or c in "_-") or "report"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = settings.paths.reports_dir

    # Markdown
    md_path = reports_dir / f"{safe}_{timestamp}.md"
    md_content = Template(MARKDOWN_TEMPLATE).render(**ctx)
    md_path.write_text(md_content, encoding="utf-8")

    paths = {"md": str(md_path)}

    # Excel
    try:
        xlsx_path = reports_dir / f"{safe}_{timestamp}.xlsx"
        export_excel(ctx, xlsx_path)
        paths["xlsx"] = str(xlsx_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Excel 导出失败: %s", exc)

    # Word
    try:
        docx_path = reports_dir / f"{safe}_{timestamp}.docx"
        export_word(ctx, docx_path)
        paths["docx"] = str(docx_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Word 导出失败: %s", exc)

    logger.info("报告已生成: %s", paths)
    return paths
