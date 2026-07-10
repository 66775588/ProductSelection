"""市场热度数据源。

搜索量、点击率、转化率等指标平台不公开，第一版以 Mock 为主；
预留 fetch_real() 接口，后续接入生意参谋/平台开放 API 时替换实现，上游不变。
"""
from __future__ import annotations

import logging

from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import MarketData

logger = logging.getLogger(__name__)


class MarketAdapter(DataSourceAdapter):
    name = "market"

    def fetch_real(self, category: str, platform: str) -> MarketData | None:
        # 预留：接入生意参谋/平台开放 API 后在此实现
        logger.info("[%s] 暂无真实数据源接口，使用 Mock", self.name)
        return None

    def fetch_mock(self, category: str, platform: str) -> MarketData:
        return mock_gen.generate_market(category)
