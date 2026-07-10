"""评论/差评数据源：Playwright 爬取商品评价区。

真实爬取需进入商品详情页并触发评价加载，受登录/反爬限制；
失败/空结果由基类回退 Mock。第一版不保证真实评论完整性。
"""
from __future__ import annotations

import logging

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import CompetitorProduct, DataSource, Review
from dianshang.utils.crawler import browser_context

logger = logging.getLogger(__name__)


class ReviewAdapter(DataSourceAdapter):
    name = "reviews"

    def __init__(self, force_mock: bool | None = None, max_per_product: int = 10) -> None:
        super().__init__(force_mock=force_mock)
        self.max_per_product = max_per_product

    def fetch_real(self, category: str, platform: str) -> list[Review] | None:
        # 需要「先抓竞品→再逐个进详情页抓评价」的两步流程，
        # 依赖登录态且耗时高，第一版直接回退 Mock 以保证可演示。
        # 真实接入时：遍历竞品 url，goto 详情页，点击「评价」tab，解析评价区。
        logger.info("[%s] 两步抓取未启用，回退 Mock", self.name)
        return None

    def fetch_mock(self, category: str, platform: str) -> list[Review]:
        return mock_gen.generate_reviews(category)
