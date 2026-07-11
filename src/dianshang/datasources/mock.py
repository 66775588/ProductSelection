"""确定性 Mock 数据生成器。

以品类字符串为种子，保证同一品类多次运行结果可复现（便于测试与调参）。
数值基于品类的合理量级估算，并非真实数据——所有记录 source 标记为 MOCK，
报告渲染时会据此标注「（模拟）」。
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from dianshang.datasources.models import (
    CompetitorProduct,
    DataSource,
    MarketData,
    Review,
    SupplySource,
    TrendPoint,
)

# 通用电商差评痛点词库（LLM 聚类时会被归并为 TOP 痛点）
PAIN_KEYWORDS = [
    "材质偏薄", "做工粗糙", "有异味", "用几天就坏了", "容量比想象小",
    "漏水", "掉色", "尺寸不准", "包装简陋", "物流慢",
    "客服态度差", "性价比低", "与描述不符", "颜色有色差", "手感一般",
    "密封性差", "容易刮花", "配件缺失", "说明书不清楚", "耐久性差",
]

POSITIVE_KEYWORDS = [
    "颜值高", "做工精致", "性价比高", "物流快", "包装精美",
    "手感好", "容量合适", "质量不错", "推荐购买", "回购了",
]

VARIANT_WORDS = ["便携", "家用", "大容量", "迷你", "升级款", "国潮", "ins风", "商务", "学生", "车载"]


def _seeded_random(category: str) -> random.Random:
    """品类字符串 → 确定性随机数生成器。"""
    seed = int(hashlib.md5(category.encode("utf-8")).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_competitors(category: str, platform: str = "pdd", n: int = 20) -> list[CompetitorProduct]:
    rng = _seeded_random(category)
    # 平台基础域名（占位链接）
    _PLATFORM_URLS: dict[str, str] = {
        "pdd": "https://mobile.yangkeduo.com/goods.html?goods_id=mock_{pid}",
        "taobao": "https://item.taobao.com/item.htm?id=mock_{pid}",
        "tmall": "https://detail.tmall.com/item.htm?id=mock_{pid}",
        "jd": "https://item.jd.com/mock_{pid}.html",
    }
    url_tpl = _PLATFORM_URLS.get(platform, _PLATFORM_URLS["pdd"])
    # 价格带：基于品类哈希落在 15~150 元区间
    base_price = 15 + (rng.random() * 135)
    competitors: list[CompetitorProduct] = []
    for i in range(n):
        pid = 100000 + i * 7 + hash(category + str(i)) % 900000
        price = round(base_price * rng.uniform(0.6, 1.8), 1)
        # 销量幂律分布：头部远高于尾部
        sales = int(rng.randint(50, 500) * (1.6 ** (n - i)) * rng.uniform(0.7, 1.3))
        sales = min(sales, 100000)
        review_count = int(sales * rng.uniform(0.05, 0.2))
        competitors.append(
            CompetitorProduct(
                rank=i + 1,
                title=f"{category}{rng.choice(VARIANT_WORDS)}款{i+1}",
                price=price,
                sales=sales,
                shop_name=f"{rng.choice(['旗舰', '专营', '官方', '优选'])}店{rng.randint(1,99)}",
                shop_level=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 25, 35, 25])[0],
                sku_count=rng.randint(1, 15),
                review_count=review_count,
                url=url_tpl.format(pid=pid),
                tags=rng.sample(VARIANT_WORDS, k=rng.randint(2, 4)),
                source=DataSource.MOCK,
                fetched_at=_now(),
            )
        )
    return competitors


def generate_reviews(category: str, n: int = 80) -> list[Review]:
    """生成评论，约 40% 负面（含痛点词）以便痛点聚类有素材。"""
    rng = _seeded_random(category + "reviews")
    reviews: list[Review] = []
    for i in range(n):
        is_negative = rng.random() < 0.4
        if is_negative:
            pain = rng.choice(PAIN_KEYWORDS)
            content = f"这个{category}，{pain}，{rng.choice(['有点失望', '不太满意', '建议改进', '差强人意'])}。"
            rating = rng.choice([1, 2, 2, 3])
            sentiment = "negative"
        elif rng.random() < 0.7:
            pos = rng.choice(POSITIVE_KEYWORDS)
            content = f"{category}收到了，{pos}，{rng.choice(['很满意', '会推荐给朋友', '值得入手'])}。"
            rating = rng.choice([4, 5, 5])
            sentiment = "positive"
        else:
            content = f"{category}一般般，{rng.choice(['凑合用', '没什么特别', '中规中矩'])}。"
            rating = 3
            sentiment = "neutral"
        reviews.append(
            Review(
                product_id=f"mock_{i}",
                content=content,
                rating=rating,
                sentiment=sentiment,  # type: ignore[arg-type]
                source=DataSource.MOCK,
                fetched_at=_now(),
            )
        )
    return reviews


def generate_market(category: str) -> MarketData:
    rng = _seeded_random(category + "market")
    search_volume = rng.randint(5000, 800000)
    online_products = rng.randint(1000, 500000)
    supply_demand_ratio = round(search_volume / max(online_products, 1), 2)

    # 趋势：30 天 / 90 天指数
    base_idx = rng.randint(40, 120)
    today = datetime.now(timezone.utc).date()
    trend_30d = [
        TrendPoint(date=(today - timedelta(days=29 - i)).isoformat(),
                   search_index=int(base_idx * rng.uniform(0.7, 1.3)))
        for i in range(30)
    ]
    trend_90d = [
        TrendPoint(date=(today - timedelta(days=89 - i)).isoformat(),
                   search_index=int(base_idx * rng.uniform(0.5, 1.5)))
        for i in range(90)
    ]

    long_tail = [
        (f"{category}{rng.choice(VARIANT_WORDS)}", rng.randint(500, 50000))
        for _ in range(8)
    ]
    # 蓝海/红海判断：供需比越高越蓝海
    market_type = "蓝海" if supply_demand_ratio > 2 else ("衰退" if supply_demand_ratio < 0.3 else "红海")
    seasonality = rng.choice(["旺季", "淡季", "平稳"])

    return MarketData(
        search_volume=search_volume,
        click_rate=round(rng.uniform(0.02, 0.12), 4),
        conversion_rate=round(rng.uniform(0.01, 0.08), 4),
        trend_30d=trend_30d,
        trend_90d=trend_90d,
        supply_demand_ratio=supply_demand_ratio,
        long_tail_keywords=long_tail,
        seasonality=seasonality,
        market_type=market_type,
        source=DataSource.MOCK,
        fetched_at=_now(),
    )


def generate_supply(category: str, competitors: list[CompetitorProduct] | None = None) -> list[SupplySource]:
    """1688 货源：供货价约为竞品中位价 40~55%。"""
    rng = _seeded_random(category + "supply")
    if competitors:
        prices = [c.price for c in competitors]
        median_price = sorted(prices)[len(prices) // 2]
    else:
        median_price = 50.0
    sources: list[SupplySource] = []
    for i in range(5):
        supply_price = round(median_price * rng.uniform(0.40, 0.55), 2)
        pid = 6000000000 + hash(category + str(i)) % 9000000000
        sources.append(
            SupplySource(
                product_name=f"{category}代发款{i+1}",
                supply_price=supply_price,
                moq=rng.choice([1, 2, 5, 10, 50, 100]),
                delivery_days=rng.choice([1, 2, 3, 5, 7]),
                supplier_level=rng.choices([1, 2, 3], weights=[20, 50, 30])[0],
                url=f"https://detail.1688.com/offer/{pid}.html",
                source=DataSource.MOCK,
                fetched_at=_now(),
            )
        )
    return sources
