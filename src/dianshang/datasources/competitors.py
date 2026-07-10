"""竞品列表数据源：Playwright 爬取平台公开搜索结果。

真实爬取受平台反爬/登录限制，成功率不保证；任何失败/空结果由基类回退 Mock。
第一版以「能跑通 + 可演示」为目标，不保证真实数据完整性。
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

from dianshang.config import settings
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.base import DataSourceAdapter
from dianshang.datasources.models import CompetitorProduct, DataSource
from dianshang.utils.crawler import browser_context

logger = logging.getLogger(__name__)

# 各平台公开搜索页 URL 模板（移动版更易解析）
SEARCH_URLS: dict[str, str] = {
    "pdd": "https://mobile.yangkeduo.com/search_result.html?search_key={kw}",
    "taobao": "https://s.taobao.com/search?q={kw}",
    "tmall": "https://list.tmall.com/search_product.htm?q={kw}",
    "jd": "https://search.jd.com/Search?keyword={kw}",
}

# 价格提取：匹配「¥12.3」「12.3元」「￥12」等
_PRICE_RE = re.compile(r"[¥￥]?\s*(\d+(?:\.\d{1,2})?)")
_SALES_RE = re.compile(r"已售\s*([\d.]+)\s*([万千]?)|月销\s*([\d.]+)\s*([万千]?)")


def _parse_sales(text: str) -> int:
    m = _SALES_RE.search(text or "")
    if not m:
        return 0
    num = float(m.group(1) or m.group(3) or 0)
    unit = m.group(2) or m.group(4)
    if unit == "万":
        num *= 10000
    elif unit == "千":
        num *= 1000
    return int(num)


class CompetitorAdapter(DataSourceAdapter):
    name = "competitors"

    def fetch_real(self, category: str, platform: str) -> list[CompetitorProduct] | None:
        url_tpl = SEARCH_URLS.get(platform)
        if not url_tpl:
            logger.warning("[%s] 不支持的平台 %s，回退 Mock", self.name, platform)
            return None
        url = url_tpl.format(kw=quote(category))
        logger.info("[%s] 抓取 %s", self.name, url)
        try:
            with browser_context() as page:
                page.goto(url, wait_until="domcontentloaded", timeout=settings.crawl.timeout * 1000)
                page.wait_for_timeout(2500)  # 等动态内容加载
                # 候选商品卡片选择器（多平台兼容）
                card_selectors = [
                    "[class*='goods-item']", "[class*='product-item']",
                    "[class*='search-item']", ".gl-item", ".J_MouserOnverReq",
                    "div[data-spm]", "li.gl-item",
                ]
                cards: list = []
                for sel in card_selectors:
                    cards = page.query_selector_all(sel)
                    if cards:
                        break
                if not cards:
                    logger.warning("[%s] 未匹配到商品卡片（可能需登录/反爬），回退 Mock", self.name)
                    return None
                products: list[CompetitorProduct] = []
                for idx, card in enumerate(cards[:20]):
                    text = card.inner_text() or ""
                    price_match = _PRICE_RE.search(text)
                    if not price_match:
                        continue
                    price = float(price_match.group(1))
                    sales = _parse_sales(text)
                    title = text.split("\n")[0][:60].strip() or f"{category}商品{idx+1}"
                    products.append(
                        CompetitorProduct(
                            rank=idx + 1,
                            title=title,
                            price=price,
                            sales=sales,
                            shop_name="",
                            shop_level=0,
                            sku_count=0,
                            review_count=int(sales * 0.1),
                            source=DataSource.REAL_SCRAPE,
                        )
                    )
                if not products:
                    return None
                logger.info("[%s] 真实抓取到 %d 个竞品", self.name, len(products))
                return products
        except Exception as exc:  # noqa: BLE001 —— 由基类回退
            logger.warning("[%s] 抓取异常: %s", self.name, exc)
            return None

    def fetch_mock(self, category: str, platform: str) -> list[CompetitorProduct]:
        return mock_gen.generate_competitors(category)
