"""1688 供应链货源数据源。

供货价/起订量通过 1688 开放平台「分销商品关键词搜索」接口获取，
需在 Web 设置页配置 AppKey/AppSecret；未配置或调用失败时自动回退 Mock。

接口与签名说明（open.1688.com 官方文档，2026-10 核实）：
- 请求地址：POST https://gw.open.1688.com/openapi/param2/1/com.alibaba.fenxiao/product.keywords.search/{AppKey}
- 业务参数：param = FenXiaoKeyWordSearchParam 的 JSON 字符串（keyword/pageNo/pageSize）
- 签名算法（param2 风格，与阿里开放平台 TOP 一致）：
  除 _aop_signature 外所有请求参数按参数名 ASCII 升序排序，
  拼接为 key+value 连续字符串，前后包裹 AppSecret 后取 MD5（32 位大写）。
  注：原实现使用的 SHA256 简化签名不符合官方规范，已替换为 MD5。
"""
from __future__ import annotations

import hashlib
import json
import logging

import requests

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import CompetitorProduct, DataSource, SupplySource

logger = logging.getLogger(__name__)

ALIBABA_1688_API = "https://gw.open.1688.com/openapi/param2/1"
FENXIAO_KEYWORD_SEARCH = "com.alibaba.fenxiao/product.keywords.search"


def _sign_1688(app_secret: str, params: dict) -> str:
    """1688 开放平台（param2 风格）官方 MD5 签名。"""
    raw = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    payload = f"{app_secret}{raw}{app_secret}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest().upper()


def _deep_get(data: dict, *paths) -> object | None:
    """按候选路径依次取值，兼容 1688 响应结构字段名差异。"""
    for path in paths:
        node = data
        ok = True
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                ok = False
                break
        if ok:
            return node
    return None


def _to_int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_price(value) -> float:
    """兼容 '12.5-18.0' / '12.5' / 数字 的供货价解析。"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).split("-")[0].strip())
    except (TypeError, ValueError):
        return 0.0


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
            biz_param = json.dumps(
                {"keyword": category, "pageNo": 1, "pageSize": 20},
                ensure_ascii=False,
            )
            params = {"param": biz_param}
            params["_aop_signature"] = _sign_1688(app_secret, params)

            resp = requests.post(
                f"{ALIBABA_1688_API}/{FENXIAO_KEYWORD_SEARCH}/{app_key}",
                params=params,
                timeout=settings.crawl.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            result = _deep_get(data, ("result",)) or data
            items = _deep_get(result, ("resultList",), ("products",), ("items",), ("list",))
            if not items:
                logger.warning("[%s] 1688 API 返回空结果", self.name)
                return None

            products: list[SupplySource] = []
            for idx, item in enumerate(items):
                products.append(SupplySource(
                    product_name=_deep_get(item, ("subject",), ("productName",)) or f"{category}货源{idx+1}",
                    supply_price=_parse_price(_deep_get(item, ("priceRange",), ("price",), ("minPrice",), ("supplyPrice",))),
                    moq=_to_int(_deep_get(item, ("minOrderQuantity",), ("moq",), ("startQuantity",))) or 1,
                    delivery_days=_to_int(_deep_get(item, ("deliveryTime",), ("deliveryDays",))) or 7,
                    supplier_level=2,
                    url=_deep_get(item, ("detailUrl",), ("productDetailUrl",), ("offerDetailUrl",)) or "",
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
