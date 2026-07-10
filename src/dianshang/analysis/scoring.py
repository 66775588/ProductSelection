"""五维评分模型：各维度 0-100 → 加权综合得分 → 推荐等级。

评分规则透明、可单测。命中红线（禁售/侵权高危）直接短路为「不推荐」。
"""
from __future__ import annotations

from typing import Any

from dianshang.config import settings


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_market(market: dict[str, Any] | None) -> float:
    if not market:
        return 50.0  # 数据不足给中位
    sdr = market.get("supply_demand_ratio", 1.0)
    # 供需比越高越蓝海
    sdr_score = _clamp(40 + sdr * 25)  # SDR=0→40, =2→90, =2.4→100
    # 趋势：30d 末值 vs 首值
    trend = market.get("trend_30d") or []
    if len(trend) >= 2:
        first, last = trend[0].get("search_index", 0), trend[-1].get("search_index", 0)
        growth = (last - first) / max(first, 1)
        growth_score = _clamp(50 + growth * 200)  # +25%→100, -25%→0
    else:
        growth_score = 50.0
    mtype = market.get("market_type", "红海")
    type_bonus = {"蓝海": 15, "红海": 0, "衰退": -20}.get(mtype, 0)
    return _clamp(sdr_score * 0.5 + growth_score * 0.5 + type_bonus)


def score_competition(competitors: list[dict[str, Any]]) -> float:
    if not competitors:
        return 50.0
    sales = [c.get("sales", 0) for c in competitors]
    total = sum(sales) or 1
    top3_share = sum(sorted(sales, reverse=True)[:3]) / total  # 头部垄断率
    # 垄断率越高 → 进入越难 → 分数越低
    monopoly_score = _clamp(100 - top3_share * 100)
    avg_sales = sum(sales) / len(sales)
    # 平均销量过高 → 红海；过低 → 需求弱。适中最好
    if avg_sales > 20000:
        volume_score = 40.0
    elif avg_sales < 200:
        volume_score = 50.0
    else:
        volume_score = 80.0
    return _clamp(monopoly_score * 0.6 + volume_score * 0.4)


def score_profit(profit: dict[str, Any] | None) -> float:
    if not profit:
        return 50.0
    margin = profit.get("gross_margin", 0)  # 百分比
    threshold = profit.get("threshold", settings.profit.profit_threshold)
    # margin>=50→100, threshold→60, 0→0
    if margin >= 50:
        return 100.0
    if margin >= threshold:
        return _clamp(60 + (margin - threshold) / max(50 - threshold, 1) * 40)
    return _clamp(margin / max(threshold, 1) * 60)


def score_pain_points(pain_points: list[dict[str, Any]]) -> float:
    """痛点越多越严重 → 差异化机会越大 → 分数越高。"""
    if not pain_points:
        return 40.0  # 无痛点数据，机会不明
    n = len(pain_points)
    high = sum(1 for p in pain_points if p.get("severity") == "高")
    # 痛点数量 + 高严重度占比
    count_score = _clamp(n / 10 * 70 + 30)
    severity_score = _clamp(n and (high / n * 100))
    return _clamp(count_score * 0.6 + severity_score * 0.4)


def score_risk(risk_items: list[dict[str, Any]], red_line_hit: bool) -> float:
    if red_line_hit:
        return 0.0
    if not risk_items:
        return 90.0
    high = sum(1 for r in risk_items if r.get("level") == "高")
    mid = sum(1 for r in risk_items if r.get("level") == "中")
    penalty = high * 20 + mid * 8
    return _clamp(90 - penalty)


def compute_scores(
    market: dict[str, Any] | None,
    competitors: list[dict[str, Any]],
    profit: dict[str, Any] | None,
    pain_points: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    red_line_hit: bool,
) -> dict[str, Any]:
    """计算五维分数与综合得分，返回推荐等级。"""
    w = settings.scoring_weights
    dims = {
        "market_potential": score_market(market),
        "competition": score_competition(competitors),
        "profit": score_profit(profit),
        "pain_points": score_pain_points(pain_points),
        "risk": score_risk(risk_items, red_line_hit),
    }
    total = (
        dims["market_potential"] * w.market_potential
        + dims["competition"] * w.competition
        + dims["profit"] * w.profit
        + dims["pain_points"] * w.pain_points
        + dims["risk"] * w.risk
    )
    total = round(total, 1)

    th = settings.score_thresholds
    if red_line_hit:
        recommendation = "不推荐"
        reason = "命中红线规则（禁售/侵权高危品类）"
    elif total >= th.strong_recommend:
        recommendation = "强烈推荐"
        reason = f"综合得分 {total} 达到强烈推荐阈值"
    elif total >= th.try_it:
        recommendation = "可尝试"
        reason = f"综合得分 {total}，具备切入价值但需关注短板"
    elif total >= th.cautious:
        recommendation = "谨慎进入"
        reason = f"综合得分 {total}，风险或竞争压力较大"
    else:
        recommendation = "不推荐"
        reason = f"综合得分 {total} 偏低"

    return {
        "dimensions": {k: round(v, 1) for k, v in dims.items()},
        "weights": {
            "market_potential": w.market_potential,
            "competition": w.competition,
            "profit": w.profit,
            "pain_points": w.pain_points,
            "risk": w.risk,
        },
        "total_score": total,
        "recommendation": recommendation,
        "reason": reason,
    }
