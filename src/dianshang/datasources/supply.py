"""1688 供应链货源数据源。

供货价/起订量需登录 1688 或调用其开放 API，第一版以 Mock 为主；
预留 fetch_real()，后续接入 1688 API 时替换。
"""
from __future__ import annotations

import logging

from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import CompetitorProduct, SupplySource

logger = logging.getLogger(__name__)


class SupplyAdapter(DataSourceAdapter):
    name = "supply"

    def __init__(self, force_mock: bool | None = None, competitors: list[CompetitorProduct] | None = None) -> None:
        super().__init__(force_mock=force_mock)
        self._competitors = competitors

    def fetch_real(self, category: str, platform: str) -> list[SupplySource] | None:
        # 预留：接入 1688 开放 API (AppKey/Secret) 后在此实现
        logger.info("[%s] 暂无 1688 真实接口，使用 Mock", self.name)
        return None

    def fetch_mock(self, category: str, platform: str) -> list[SupplySource]:
        return mock_gen.generate_supply(category, self._competitors)
