"""GLM（智谱）客户端封装：结构化 JSON 输出、tenacity 重试、降级。

无 API Key 或调用失败时，调用方应提供确定性降级逻辑（基于规则/统计），
保证流水线不因 LLM 不可用而中断。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from dianshang.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """智谱 GLM 调用封装。"""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.llm.api_key
        self.model = model or settings.llm.model
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from zhipuai import ZhipuAI  # type: ignore

            self._client = ZhipuAI(api_key=self.api_key)
        return self._client

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _chat(self, system: str, user: str) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=settings.llm.temperature,
            timeout=settings.llm.timeout,
        )
        return resp.choices[0].message.content or ""

    def chat(self, system: str, user: str) -> str:
        """普通对话，返回文本。无 Key 时抛 RuntimeError。"""
        if not self.available:
            raise RuntimeError("未配置 ZHIPUAI_API_KEY，LLM 不可用")
        return self._chat(system, user)

    def chat_json(self, system: str, user: str) -> dict[str, Any] | None:
        """对话并解析 JSON。失败返回 None（调用方降级）。"""
        try:
            text = self.chat(system, user)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 调用失败: %s", exc)
            return None
        return parse_json_loose(text)


def parse_json_loose(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中提取 JSON（容忍前后多余文字与 ```json 围栏）。"""
    if not text:
        return None
    # 去除代码围栏
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    # 截取第一个 { 到最后一个 }
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None


# 全局单例
llm_client = LLMClient()
