"""Playwright 浏览器上下文封装。

真实爬取平台公开搜索/评价页。受平台反爬与登录限制，成功率不保证；
适配器层会在任何失败时回退 Mock，因此本模块允许抛异常。

未安装 Playwright 浏览器时，`ensure_browser()` 抛出友好错误，由调用方捕获回退。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from dianshang.config import settings

logger = logging.getLogger(__name__)


def _import_playwright():
    """延迟导入，避免未安装时整个模块不可用。"""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:  # pragma: no cover - 环境依赖
        raise RuntimeError(
            "未安装 Playwright，请运行: pip install playwright && playwright install chromium"
        ) from exc
    return sync_playwright


@contextmanager
def browser_context(headless: bool | None = None) -> Iterator:
    """ yield 一个已就绪的 Page；退出时自动清理。"""
    sync_playwright = _import_playwright()
    headless = settings.crawl.headless if headless is None else headless
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()
