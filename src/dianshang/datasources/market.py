"""市场热度数据源。

真实接入现状（按各平台开放平台官方文档核实，2026-10）：
- 拼多多：官方网关 https://gw-api.pinduoduo.com/api/router，MD5 签名，
  调用 pdd.ddk.goods.search（多多客商品搜索），返回真实商品/销量数据；
  注意：需要「多多客 / 营销推广」类应用授权，授权不可用时自动回退 Mock。
- 生意参谋（淘宝/天猫）、京东商智：均为商家后台内部数据平台，无公开开放 API，
  原占位端点已移除；配置凭证后仍无法调用，统一回退 Mock，建议接入第三方数据服务。

未配置凭证或调用失败时自动回退 Mock（基类行为）。
"""
from __future__ import annotations

import hashlib
import logging
import time

import requests

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import DataSource, MarketData

logger = logging.getLogger(__name__)

PDD_ROUTER_API = "https://gw-api.pinduoduo.com/api/router"
PDD_GOODS_SEARCH = "pdd.ddk.goods.search"


def _pdd_sign(client_secret: str, params: dict) -> str:
    """拼多多开放平台官方 MD5 签名。

    规则（open.pinduoduo.com《签名与验签机制说明》）：
    1) 所有请求参数（公共+业务，不含 sign）按参数名 ASCII 升序排序；
    2) 拼接为 key+value 连续字符串（无分隔符）；
    3) 前后包裹 client_secret 后取 MD5，转大写。
    """
    raw = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    payload = f"{client_secret}{raw}{client_secret}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest().upper()


class MarketAdapter(DataSourceAdapter):
    name = "market"

    def fetch_real(self, category: str, platform: str) -> MarketData | None:
        cred = settings.api_credentials
        try:
            if platform in ("taobao", "tmall"):
                return self._fetch_sycm(category, cred)
            elif platform == "jd":
                return self._fetch_jd_sz(category, cred)
            elif platform == "pdd":
                return self._fetch_pdd_open(category, cred)
            else:
                logger.info("[%s] 平台 %s 暂无市场数据 API", self.name, platform)
                return None
        except Exception as exc:
            logger.warning("[%s] 市场数据 API 调用失败 (%s)，回退 Mock", self.name, exc)
            return None

    # ── 生意参谋（淘宝/天猫）：无公开开放 API ──────────────────

    def _fetch_sycm(self, category: str, cred) -> MarketData | None:
        logger.warning(
            "[%s] 生意参谋为商家后台内部数据平台，无公开开放 API（原占位端点已移除）；"
            "如需真实市场热度数据，请接入经官方授权的数据服务商或第三方数据服务，本次回退 Mock",
            self.name,
        )
        return None

    # ── 京东商智：无公开开放 API ─────────────────────────────

    def _fetch_jd_sz(self, category: str, cred) -> MarketData | None:
        logger.warning(
            "[%s] 京东商智为商家后台内部数据平台，无公开开放 API（原占位端点已移除）；本次回退 Mock",
            self.name,
        )
        return None

    # ── 拼多多开放平台（pdd.ddk.goods.search）─────────────────

    def _fetch_pdd_open(self, category: str, cred) -> MarketData | None:
        client_id = cred.pdd_client_id
        client_secret = cred.pdd_client_secret
        if not client_id or not client_secret:
            logger.info("[%s] 未配置拼多多 API 凭证", self.name)
            return None

        params = {
            "type": PDD_GOODS_SEARCH,
            "client_id": client_id,
            "timestamp": str(int(time.time())),
            "data_type": "JSON",
            "keyword": category,
            "page": "1",
            "page_size": "100",
        }
        params["sign"] = _pdd_sign(client_secret, params)

        resp = requests.post(PDD_ROUTER_API, json=params, timeout=settings.crawl.timeout)
        resp.raise_for_status()
        data = resp.json()

        if data.get("error_response"):
            err = data["error_response"]
            logger.warning(
                "[%s] 拼多多 API 错误: %s",
                self.name,
                err.get("sub_msg") or err.get("error_msg") or "",
            )
            return None

        goods_list = ((data.get("goods_search_response") or {}).get("goods_list")) or []
        if not goods_list:
            logger.warning("[%s] 拼多多 API 返回空结果", self.name)
            return None

        # 开放平台不提供搜索量/点击率/转化率等热度指标，留 0 交由评分降级；
        # market_type 按真实返回商品数粗略估算（非官方指标，报告中等同估算值）。
        total = len(goods_list)
        if total >= 80:
            market_type = "红海"
        elif total >= 40:
            market_type = "平稳"
        else:
            market_type = "蓝海"

        return MarketData(
            search_volume=0,
            click_rate=0.0,
            conversion_rate=0.0,
            trend_30d=[],
            trend_90d=[],
            supply_demand_ratio=0.0,
            long_tail_keywords=[],
            seasonality="平稳",
            market_type=market_type,  # 按商品数估算
            source=DataSource.API,
        )

    def fetch_mock(self, category: str, platform: str) -> MarketData:
        return mock_gen.generate_market(category)
