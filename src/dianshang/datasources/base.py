"""数据源适配器抽象基类。

设计原则：所有数据源（爬虫 / API / Mock）实现同一接口，
上游 Agent 节点不关心数据来自何处，由适配器自行决定真实抓取还是 Mock 回退。
"""
from __future__ import annotations

import abc
import logging
from typing import Any

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.models import Dataset

logger = logging.getLogger(__name__)


class DataSourceAdapter(abc.ABC):
    """数据源适配器基类。

    子类实现 `fetch_real()` 做真实抓取；基类 `fetch()` 负责异常兜底：
    真实抓取失败 / 空结果 / force_mock 时自动回退 Mock，并记录来源。
    """

    name: str = "base"

    def __init__(self, force_mock: bool | None = None) -> None:
        self.force_mock = settings.crawl.force_mock if force_mock is None else force_mock

    @abc.abstractmethod
    def fetch_real(self, category: str, platform: str) -> Any:
        """真实抓取实现。返回对应数据结构或 None（表示抓取失败/空）。"""
        ...

    @abc.abstractmethod
    def fetch_mock(self, category: str, platform: str) -> Any:
        """Mock 生成（默认委托给 mock 模块）。"""
        ...

    def fetch(self, category: str, platform: str) -> Any:
        """统一入口：尝试真实抓取，失败回退 Mock。"""
        if self.force_mock:
            logger.info("[%s] force_mock=True，直接使用 Mock 数据", self.name)
            return self.fetch_mock(category, platform)
        try:
            data = self.fetch_real(category, platform)
            if data is None or (hasattr(data, "__len__") and len(data) == 0):
                logger.warning("[%s] 真实抓取返回空，回退 Mock", self.name)
                return self.fetch_mock(category, platform)
            logger.info("[%s] 真实抓取成功", self.name)
            return data
        except Exception as exc:  # noqa: BLE001 —— 任意抓取异常都要兜底
            logger.warning("[%s] 真实抓取失败 (%s)，回退 Mock", self.name, exc)
            return self.fetch_mock(category, platform)


class CompositeDataSource:
    """聚合四个数据源适配器，一次性产出完整 Dataset。

    data_fetch 节点调用此类的 fetch()，内部并行（线程池）抓取四类数据。
    """

    def __init__(self, force_mock: bool | None = None) -> None:
        # 延迟导入避免循环依赖 / 避免未装 Playwright 时 import 失败
        from dianshang.datasources.competitors import CompetitorAdapter
        from dianshang.datasources.market import MarketAdapter
        from dianshang.datasources.reviews import ReviewAdapter
        from dianshang.datasources.supply import SupplyAdapter

        fm = force_mock
        self.market = MarketAdapter(force_mock=fm)
        self.competitors = CompetitorAdapter(force_mock=fm)
        self.reviews = ReviewAdapter(force_mock=fm)
        self.supply = SupplyAdapter(force_mock=fm)

    def fetch(self, category: str, platform: str) -> Dataset:
        import concurrent.futures as cf

        tasks = {
            "market": lambda: self.market.fetch(category, platform),
            "competitors": lambda: self.competitors.fetch(category, platform),
            "reviews": lambda: self.reviews.fetch(category, platform),
            "supply": lambda: self.supply.fetch(category, platform),
        }
        results: dict[str, Any] = {}
        with cf.ThreadPoolExecutor(max_workers=settings.crawl.concurrency) as pool:
            futures = {pool.submit(fn): key for key, fn in tasks.items()}
            for fut in cf.as_completed(futures):
                key = futures[fut]
                try:
                    results[key] = fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error("数据源 %s 抓取异常: %s", key, exc)
                    results[key] = None

        # 兜底：任一数据源整体失败时用 Mock 补
        market = results.get("market") or mock_gen.generate_market(category)
        competitors = results.get("competitors") or mock_gen.generate_competitors(category)
        reviews = results.get("reviews") or mock_gen.generate_reviews(category)
        supply = results.get("supply")

        # 供应链 Mock 必须与竞品价格带保持一致，否则供货价可能与售价脱节（负毛利失真）。
        # 优先用真实爬取的 supply；若为空或 Mock，则基于已抓取竞品重新生成，保证成本测算自洽。
        from dianshang.datasources.models import DataSource as _DS

        if not supply or supply[0].source == _DS.MOCK:
            supply = mock_gen.generate_supply(category, competitors)

        dataset = Dataset(
            competitors=competitors,
            reviews=reviews,
            market=market,
            supply=supply,
        )
        dataset.source_notes = _build_source_notes(dataset)
        return dataset


def _build_source_notes(ds: Dataset) -> dict[str, str]:
    """汇总每类数据来源，供报告头注使用。"""
    notes: dict[str, str] = {}

    def _label(src) -> str:
        from dianshang.datasources.models import DataSource

        return "真实爬取" if src in (DataSource.REAL_SCRAPE, DataSource.API) else "模拟数据"

    if ds.competitors:
        notes["竞品数据"] = _label(ds.competitors[0].source)
    if ds.reviews:
        notes["评论数据"] = _label(ds.reviews[0].source)
    if ds.market:
        notes["市场数据"] = _label(ds.market.source)
    if ds.supply:
        notes["供应链数据"] = _label(ds.supply[0].source)
    return notes
