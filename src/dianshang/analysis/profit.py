"""成本利润测算：全链路成本 → 毛利率 / 回本周期 / 盈亏平衡。

公式透明、可单测。所有比率来自 config.ProfitConfig。
"""
from __future__ import annotations

import statistics
from typing import Any

from dianshang.config import settings
from dianshang.datasources.models import CompetitorProduct, SupplySource


def _median(values: list[float], default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def calculate_profit(
    competitors: list[CompetitorProduct],
    supply: list[SupplySource],
) -> dict[str, Any]:
    """测算盈利空间。

    取竞品中位价为目标售价（贴近市场实价），供应链最低供货价成本。
    """
    cfg = settings.profit
    competitor_prices = [c.price for c in competitors if c.price > 0]
    supply_prices = [s.supply_price for s in supply if s.supply_price > 0]

    selling_price = _median(competitor_prices, 50.0)
    supply_price = min(supply_prices) if supply_prices else selling_price * 0.45

    # 各项成本
    commission = selling_price * cfg.platform_commission_rate
    logistics = selling_price * cfg.logistics_rate
    promotion = selling_price * cfg.promotion_rate
    refund_loss = selling_price * cfg.refund_loss_rate
    tax = selling_price * cfg.tax_rate
    packaging = cfg.packaging_cost

    total_cost = (
        supply_price + packaging + commission + logistics + promotion + refund_loss + tax
    )
    gross_profit = selling_price - total_cost
    gross_margin = gross_profit / selling_price if selling_price > 0 else 0.0

    # 销量预估：新店保守份额，按竞品中位月销的 5% 并封顶，避免高估导致回本周期失真
    competitor_sales = [c.sales for c in competitors if c.sales > 0]
    est_monthly_sales = min(max(int(_median(competitor_sales, 100) * 0.05), 30), 800)

    monthly_profit = gross_profit * est_monthly_sales

    # 首批备货成本（按 max(起订量, 200) 件估算典型小批首单）
    moq = min((s.moq for s in supply), default=10)
    first_batch_units = max(moq * 3, 200)
    initial_stock = first_batch_units * supply_price

    # 回本周期（月）：首批投入 / 月利润
    payback_months = initial_stock / monthly_profit if monthly_profit > 0 else float("inf")

    # 盈亏平衡月销量：月固定成本（推广+运营按推广费估算的固定部分）/ 单件利润
    monthly_fixed = promotion * est_monthly_sales * 0.5  # 假设推广固定占一半
    break_even_units = monthly_fixed / gross_profit if gross_profit > 0 else float("inf")

    below_threshold = gross_margin * 100 < cfg.profit_threshold

    return {
        "selling_price": round(selling_price, 2),
        "supply_price": round(supply_price, 2),
        "cost_breakdown": {
            "供货价": round(supply_price, 2),
            "包材": round(packaging, 2),
            "平台佣金": round(commission, 2),
            "物流": round(logistics, 2),
            "推广": round(promotion, 2),
            "退款损耗": round(refund_loss, 2),
            "税费": round(tax, 2),
            "合计": round(total_cost, 2),
        },
        "gross_profit": round(gross_profit, 2),
        "gross_margin": round(gross_margin * 100, 2),  # 百分比
        "est_monthly_sales": est_monthly_sales,
        "monthly_profit": round(monthly_profit, 2),
        "initial_stock_cost": round(initial_stock, 2),
        "payback_months": round(payback_months, 2) if payback_months != float("inf") else None,
        "break_even_units": round(break_even_units) if break_even_units != float("inf") else None,
        "below_threshold": below_threshold,
        "threshold": cfg.profit_threshold,
    }
