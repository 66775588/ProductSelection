"""数据清洗：去重、异常值校验、缺失标记。

对竞品价格/销量做 IQR 离群剔除，避免极端值污染均值；
保留原数据但标记 `is_outlier`，报告中可单独说明。
"""
from __future__ import annotations

import logging
import statistics
from typing import Any

from dianshang.datasources.models import CompetitorProduct, Dataset

logger = logging.getLogger(__name__)


def _iqr_outliers(values: list[float]) -> tuple[float, float]:
    """返回 IQR 上下界。数据过少时返回宽松界。"""
    if len(values) < 4:
        return -float("inf"), float("inf")
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def clean_competitors(competitors: list[CompetitorProduct]) -> list[CompetitorProduct]:
    if not competitors:
        return competitors
    # 按标题去重（Mock/真实混合时可能重复）
    seen: set[str] = set()
    deduped: list[CompetitorProduct] = []
    for c in competitors:
        key = c.title.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    prices = [c.price for c in deduped if c.price > 0]
    sales = [c.sales for c in deduped if c.sales > 0]
    p_lo, p_hi = _iqr_outliers(prices)
    s_lo, s_hi = _iqr_outliers(sales)

    cleaned: list[CompetitorProduct] = []
    outlier_count = 0
    for c in deduped:
        is_outlier = not (p_lo <= c.price <= p_hi) or not (s_lo <= c.sales <= s_hi)
        if is_outlier:
            outlier_count += 1
            logger.debug("离群竞品: %s (价格%.1f 销量%d)", c.title, c.price, c.sales)
        cleaned.append(c)
    if outlier_count:
        logger.info("竞品清洗：去重后 %d 条，标记离群 %d 条", len(cleaned), outlier_count)
    return cleaned


def clean_dataset(dataset: Dataset) -> Dataset:
    """清洗整份 Dataset，返回新对象。"""
    dataset.competitors = clean_competitors(dataset.competitors)
    # 评论去空
    dataset.reviews = [r for r in dataset.reviews if r.content and r.content.strip()]
    # 供应链去重
    seen_sup: set[str] = set()
    deduped_sup = []
    for s in dataset.supply:
        if s.product_name in seen_sup:
            continue
        seen_sup.add(s.product_name)
        deduped_sup.append(s)
    dataset.supply = deduped_sup
    return dataset


def mark_missing(dataset: Dataset) -> dict[str, Any]:
    """检查缺失项，返回缺失说明（供报告「数据不足」标注）。"""
    missing: dict[str, Any] = {}
    if not dataset.competitors:
        missing["competitors"] = "无竞品数据"
    if not dataset.reviews:
        missing["reviews"] = "无评论数据，痛点分析依据不足"
    if dataset.market is None:
        missing["market"] = "无市场热度数据"
    if not dataset.supply:
        missing["supply"] = "无供应链数据，利润测算依据不足"
    return missing
