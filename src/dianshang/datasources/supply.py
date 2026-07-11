"""1688 供应链货源数据源。

供货价/起订量通过 1688 开放 API 获取，需在 Web 设置页配置 AppKey/AppSecret；
未配置或调用失败时自动回退 Mock。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from urllib.parse import urlencode

import requests

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import CompetitorProduct, DataSource, SupplySource

logger = logging.getLogger(__name__)

ALIBABA_1688_API = "https://gw.open.1688.com/openapi/param2/1"


def _sign_1688(app_key: str, app_secret: str, params: dict) -> str:
    """1688 开放 API 签名算法。"""
    sorted_params = sorted(params.items())
    raw = app_secret + "".join(f"{k}{v}" for k, v in sorted_params) + app_secret
    return hashlib.sha256(raw.encode()).hexdigest().upper()


class SupplyAdapter(DataSourceAdapter):
    name = "supply"

    def __init__(self, force_mock: bool | None = None, competitors: list[CompetitorProduct] | None = None) -> None:
        super().__init__(force_mock=force_mock)
        self._competitors = competitors

    def fetch_real(self, category: str, platform: str) -> list[SupplySource] | None:
        cred = settings.api_credentials
        app_key = cred.alibaba_1688_app_key
        app_secret = cred.alibaba_1688_app_secret

        if not app_key or not app_secret:
            logger.info("[%s] 未配置 1688 API 凭证，回退 Mock", self.name)
            return None

        try:
            timestamp = str(int(time.time() * 1000))
            params = {
                "app_key": app_key,
                "timestamp": timestamp,
                "v": "2.0",
                "method": "alibaba.icbu.product.search",
                "keyword": category,
                "page_size": "20",
            }
            params["_aop_signature"] = _sign_1688(app_key, app_secret, params)

            resp = requests.get(
                f"{ALIBABA_1688_API}/{app_key}",
                params=params,
                timeout=settings.crawl.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data.get("result"):
                logger.warning("[%s] 1688 API 返回空结果", self.name)
                return None

            items = data.get("result", {}).get("items", [])
            products: list[SupplySource] = []
            for idx, item in enumerate(items):
                products.append(SupplySource(
                    product_name=item.get("subject", f"{category}货源{idx+1}"),
                    supply_price=float(item.get("priceRange", "0").split("-")[0] or 0),
                    moq=int(item.get("minOrderQuantity", 1)),
                    delivery_days=int(item.get("deliveryTime", 7)),
                    supplier_level=2,
                    url=item.get("detailUrl", ""),
                    source=DataSource.API,
                ))

            if not products:
                return None
            logger.info("[%s] 1688 API 返回 %d 条货源", self.name, len(products))
            return products

        except Exception as exc:
            logger.warning("[%s] 1688 API 调用失败 (%s)，回退 Mock", self.name, exc)
            return None

    def fetch_mock(self, category: str, platform: str) -> list[SupplySource]:
        return mock_gen.generate_supply(category, self._competitors)
