"""数据模型：各数据源的结构化数据 + 来源溯源（provenance）。

每条记录都带 `source` 字段标识数据来源（real_scrape / mock / api），
报告中据此标注「（模拟）」，杜绝将模拟数据当作真实数据呈现。
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    """数据来源标记。"""

    REAL_SCRAPE = "real_scrape"  # Playwright 爬取的公开页面数据
    API = "api"  # 平台/第三方开放 API（预留）
    MOCK = "mock"  # 模拟生成器


class ProvenanceMixin(BaseModel):
    """所有数据记录混入的来源元信息。"""

    source: DataSource = DataSource.MOCK
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompetitorProduct(ProvenanceMixin):
    """竞品商品（TOP20 之一）。"""

    rank: int
    title: str
    price: float = Field(description="客单价（元）")
    sales: int = Field(description="近30天销量")
    shop_name: str
    shop_level: int = Field(description="店铺等级 1-5")
    sku_count: int = Field(description="SKU 数")
    review_count: int = Field(default=0, description="累计评价数")
    url: str = ""
    tags: list[str] = Field(default_factory=list, description="卖点标签")


class Review(ProvenanceMixin):
    """单条评论。"""

    product_id: str = ""
    content: str
    rating: int = Field(ge=1, le=5, description="1-5 星")
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"


class TrendPoint(BaseModel):
    """搜索趋势单点。"""

    date: str  # YYYY-MM-DD
    search_index: int = Field(description="搜索热度指数")


class MarketData(ProvenanceMixin):
    """市场热度数据。"""

    search_volume: int = Field(description="近30天搜索量")
    click_rate: float = Field(description="点击率")
    conversion_rate: float = Field(description="转化率")
    trend_30d: list[TrendPoint] = Field(default_factory=list)
    trend_90d: list[TrendPoint] = Field(default_factory=list)
    supply_demand_ratio: float = Field(description="供需比 = 搜索量/在线商品数")
    long_tail_keywords: list[tuple[str, int]] = Field(
        default_factory=list, description="(长尾词, 搜索量)"
    )
    seasonality: str = "平稳"  # 旺季/淡季/平稳
    market_type: str = "红海"  # 蓝海/红海/衰退


class SupplySource(ProvenanceMixin):
    """1688 供应链货源。"""

    product_name: str
    supply_price: float = Field(description="供货价（元）")
    moq: int = Field(description="起订量")
    delivery_days: int = Field(description="发货时效（天）")
    supplier_level: int = Field(default=1, description="供应商等级 1-3")
    url: str = ""


class Dataset(BaseModel):
    """单次抓取的数据集合 + 整体来源标记。"""

    competitors: list[CompetitorProduct] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    market: Optional[MarketData] = None
    supply: list[SupplySource] = Field(default_factory=list)
    # 每类数据的来源汇总（用于报告头注）
    source_notes: dict[str, str] = Field(default_factory=dict)

    def is_any_real(self) -> bool:
        sources = {c.source for c in self.competitors}
        sources |= {r.source for r in self.reviews}
        sources |= {s.source for s in self.supply}
        if self.market:
            sources.add(self.market.source)
        return DataSource.REAL_SCRAPE in sources or DataSource.API in sources
