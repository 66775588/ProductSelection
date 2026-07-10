"""HTTP 会话：httpx + tenacity 重试，供静态请求复用。"""
from __future__ import annotations

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from dianshang.config import settings

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def get_client(timeout: int | None = None) -> httpx.Client:
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=timeout or settings.crawl.timeout,
        follow_redirects=True,
    )


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, OSError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def fetch_text(url: str, **kwargs) -> str:
    """带重试的 GET，返回响应文本。"""
    with get_client() as client:
        resp = client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text
