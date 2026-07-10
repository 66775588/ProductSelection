"""用户痛点聚类：LLM 语义聚类 + 关键词统计降级。

LLM 可用时调用 GLM 做深度语义聚类；不可用时用基于 PAIN_KEYWORDS 的词频统计降级，
保证流水线在无 Key 时仍能输出可解释的痛点清单。
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from dianshang.agent.prompts import PAIN_POINT_PROMPT, SYSTEM_PROMPT, format_prompt
from dianshang.analysis.llm import llm_client, parse_json_loose
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.models import Review

logger = logging.getLogger(__name__)


def _source_label(reviews: list[Review]) -> str:
    if not reviews:
        return "无"
    return "真实爬取" if reviews[0].source.value == "real_scrape" else "模拟数据"


def cluster_pain_points(category: str, reviews: list[Review]) -> list[dict[str, Any]]:
    """返回 TOP10 痛点列表，每项 {keyword, frequency, severity, sample}。"""
    if not reviews:
        return []
    source = _source_label(reviews)
    # 先尝试 LLM
    if llm_client.available:
        result = _cluster_via_llm(category, reviews, source)
        if result:
            return result
        logger.warning("LLM 痛点聚类失败，降级为词频统计")
    return _cluster_via_stats(reviews)


def _cluster_via_llm(category: str, reviews: list[Review], source: str) -> list[dict[str, Any]] | None:
    # 控制输入长度，取负面+部分正面
    neg = [r for r in reviews if r.sentiment == "negative"]
    sample_reviews = neg[:60] + [r for r in reviews if r.sentiment != "negative"][:20]
    review_text = "\n".join(f"- ({r.rating}星) {r.content}" for r in sample_reviews)
    prompt = format_prompt(
        PAIN_POINT_PROMPT, category=category, reviews=review_text, source=source
    )
    data = llm_client.chat_json(SYSTEM_PROMPT, prompt)
    if not data:
        return None
    points = data.get("pain_points", [])
    # 规范化字段
    normalized = []
    for p in points[:10]:
        normalized.append(
            {
                "keyword": str(p.get("keyword", "")).strip(),
                "frequency": int(p.get("frequency", 0) or 0),
                "severity": str(p.get("severity", "中")),
                "sample": str(p.get("sample", "")),
            }
        )
    return normalized


def _cluster_via_stats(reviews: list[Review]) -> list[dict[str, Any]]:
    """词频统计降级：在负面评论中匹配痛点词库。"""
    neg_reviews = [r for r in reviews if r.sentiment == "negative"]
    counter: Counter[str] = Counter()
    samples: dict[str, str] = {}
    for r in neg_reviews:
        for kw in mock_gen.PAIN_KEYWORDS:
            if kw in r.content:
                counter[kw] += 1
                samples.setdefault(kw, r.content)
    # 若词库命中少，回退到分词高频名词（简易：取 2-4 字片段）
    if sum(counter.values()) < 3:
        for r in neg_reviews:
            for kw in _extract_fragments(r.content):
                counter[kw] += 1
                samples.setdefault(kw, r.content)
    top = counter.most_common(10)
    total = sum(counter.values()) or 1
    result = []
    for kw, freq in top:
        sev = "高" if freq / total > 0.2 else ("中" if freq / total > 0.1 else "低")
        result.append(
            {
                "keyword": kw,
                "frequency": freq,
                "severity": sev,
                "sample": samples.get(kw, ""),
            }
        )
    return result


def _extract_fragments(text: str) -> list[str]:
    """简易中文片段提取：连续 2-4 个中文字符。"""
    import re

    return re.findall(r"[一-龥]{2,4}", text)
