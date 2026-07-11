"""市场热度数据源。

搜索量、点击率、转化率等指标通过各平台开放 API 获取（生意参谋/京东商智/拼多多开放平台），
需在 Web 设置页配置对应凭证；未配置或调用失败时自动回退 Mock。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import DataSource, MarketData, TrendPoint

logger = logging.getLogger(__name__)

# 各平台市场数据 API 端点（预留）
SYCM_API = "https://sycm.taobao.com/api/v1/market/hot"
JD_SZ_API = "https://sz.jd.com/api/v1/category/trend"
PDD_OPEN_API = "https://gw-api.pinduoduo.com/market/search"


class MarketAdapter(DataSourceAdapter):
    name = "market"

    def fetch_real(self, category: str, platform: str) -> MarketData | None:
        """按平台选择对应 API 数据源。"""
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

    # ── 生意参谋（淘宝/天猫）─────────────────────────────────

    def _fetch_sycm(self, category: str, cred: Any) -> MarketData | None:
        token = cred.sheng_yi_can_token
        cookie = cred.sheng_yi_can_cookie
        if not token and not cookie:
            logger.info("[%s] 未配置生意参谋凭证", self.name)
            return None
        try:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            if cookie:
                headers["Cookie"] = cookie
            resp = requests.get(
                SYCM_API,
                params={"keyword": category, "period": "30d"},
                headers=headers,
                timeout=settings.crawl.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("data"):
                return None
            d = data["data"]
            return MarketData(
                search_volume=int(d.get("searchUv", 0)),
                click_rate=float(d.get("clickRate", 0)),
                conversion_rate=float(d.get("payRate", 0)),
                trend_30d=self._parse_trend_points(d.get("trend", [])),
                trend_90d=[],
                supply_demand_ratio=float(d.get("supplyDemandRatio", 0)),
                long_tail_keywords=self._parse_keywords(d.get("longTailWords", [])),
                seasonality=d.get("seasonality", "平稳"),
                market_type=d.get("marketType", "红海"),
                source=DataSource.API,
            )
        except Exception:
            raise  # re-raise to base handler

    # ── 京东商智 ───────────────────────────────────────────

    def _fetch_jd_sz(self, category: str, cred: Any) -> MarketData | None:
        app_key = cred.jd_shangzhi_app_key
        app_secret = cred.jd_shangzhi_app_secret
        if not app_key or not app_secret:
            logger.info("[%s] 未配置京东商智凭证", self.name)
            return None
        try:
            ts = str(int(time.time() * 1000))
            resp = requests.post(
                JD_SZ_API,
                json={"appKey": app_key, "appSecret": app_secret, "timestamp": ts, "keyword": category},
                timeout=settings.crawl.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                return None
            d = data.get("result", {})
            return MarketData(
                search_volume=int(d.get("searchVolume", 0)),
                click_rate=float(d.get("ctr", 0)),
                conversion_rate=float(d.get("cvr", 0)),
                trend_30d=[],
                trend_90d=[],
                supply_demand_ratio=float(d.get("ratio", 0)),
                long_tail_keywords=[],
                seasonality="平稳",
                market_type="红海",
                source=DataSource.API,
            )
        except Exception:
            raise

    # ── 拼多多开放平台 ─────────────────────────────────────

    def _fetch_pdd_open(self, category: str, cred: Any) -> MarketData | None:
        client_id = cred.pdd_client_id
        client_secret = cred.pdd_client_secret
        if not client_id or not client_secret:
            logger.info("[%s] 未配置拼多多 API 凭证", self.name)
            return None
        try:
            ts = str(int(time.time()))
            resp = requests.post(
                PDD_OPEN_API,
                json={"client_id": client_id, "client_secret": client_secret, "timestamp": ts, "type": "pdd.goods.search.heat", "keyword": category},
                timeout=settings.crawl.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error_response"):
                logger.warning("[%s] 拼多多 API 错误: %s", self.name, data["error_response"].get("error_msg", ""))
                return None
            d = data.get("goods_heat_response", {})
            return MarketData(
                search_volume=int(d.get("search_volume", 0)),
                click_rate=float(d.get("click_rate", 0)),
                conversion_rate=float(d.get("conversion_rate", 0)),
                trend_30d=[],
                trend_90d=[],
                supply_demand_ratio=float(d.get("supply_demand", 0)),
                long_tail_keywords=[],
                seasonality="平稳",
                market_type="红海",
                source=DataSource.API,
            )
        except Exception:
            raise

    # ── 工具 ───────────────────────────────────────────────

    def _parse_trend_points(self, raw: list[dict]) -> list[TrendPoint]:
        points: list[TrendPoint] = []
        for p in raw:
            points.append(TrendPoint(
                date=str(p.get("date", "")),
                search_index=int(p.get("index", 0)),
            ))
        return points

    def _parse_keywords(self, raw: list[dict]) -> list[tuple[str, int]]:
        return [(kw.get("word", ""), int(kw.get("volume", 0))) for kw in raw[:20]]

    def fetch_mock(self, category: str, platform: str) -> MarketData:
        return mock_gen.generate_market(category)
