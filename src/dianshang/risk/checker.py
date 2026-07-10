"""风险排查：侵权/合规/供应链风险。规则库 + LLM 判断。

命中禁售/侵权高危品类（红线）直接 red_line_hit=True，评分短路为「不推荐」。
"""
from __future__ import annotations

import logging
from typing import Any

from dianshang.agent.prompts import RISK_PROMPT, SYSTEM_PROMPT, format_prompt
from dianshang.analysis.llm import llm_client

logger = logging.getLogger(__name__)

# 禁售品（平台普遍禁售）—— 命中即红线
BANNED_KEYWORDS = [
    "枪支", "弹药", "管制刀具", "爆炸物", "毒品", "易燃易爆",
    "医疗器械", "处方药", "烟草", "电子烟", "野生动物", "象牙",
    "仿真枪", "警用器械", "窃听器", "假证", "赌博设备",
]

# 侵权高危品类（知名品牌垄断/专利密集）—— 命中即红线
INFRINGEMENT_KEYWORDS = [
    "苹果", "华为", "小米", "耐克", "阿迪达斯", "LV", "香奈儿",
    "迪士尼", "漫威", "乐高", "任天堂", "索尼", "三星",
    "戴森", "罗技", "罗意威",
]

# 质量相关痛点词（用于供应链风险判断）
QUALITY_PAIN_KEYWORDS = [
    "做工粗糙", "材质偏薄", "用几天就坏了", "容易刮花", "耐久性差",
    "掉色", "漏水", "密封性差", "有异味",
]


def check_risks(
    category: str,
    pain_points: list[dict[str, Any]],
    supply: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """返回 (风险清单, 是否命中红线)。"""
    risk_items: list[dict[str, Any]] = []
    red_line = False

    # 1. 禁售品红线
    for kw in BANNED_KEYWORDS:
        if kw in category:
            risk_items.append(
                {"type": "合规", "level": "高", "desc": f"品类含禁售关键词「{kw}」",
                 "mitigation": "更换品类，平台禁售"}
            )
            red_line = True

    # 2. 侵权高危红线
    for kw in INFRINGEMENT_KEYWORDS:
        if kw in category:
            risk_items.append(
                {"type": "侵权", "level": "高", "desc": f"品类含知名品牌「{kw}」，侵权高危",
                 "mitigation": "避开品牌词，做白牌或自有品牌；核查专利商标"}
            )
            red_line = True

    # 3. 供应链质量风险（基于痛点）
    quality_points = [
        p for p in pain_points
        if any(kw in p.get("keyword", "") for kw in QUALITY_PAIN_KEYWORDS)
    ]
    if len(quality_points) >= 2:
        risk_items.append(
            {"type": "供应链", "level": "中",
             "desc": f"差评集中在质量问题（{len(quality_points)} 项），货源稳定性存疑",
             "mitigation": "筛选高等级供应商，小批量试单验证品质，强化质检"}
        )

    # 4. 供应链交付风险
    delivery_days = [s.get("delivery_days", 0) for s in supply if s.get("delivery_days")]
    if delivery_days and max(delivery_days) >= 7:
        risk_items.append(
            {"type": "供应链", "level": "低",
             "desc": f"部分货源发货时效偏长（最长 {max(delivery_days)} 天）",
             "mitigation": "优先选择 48 小时内发货供应商，备安全库存"}
        )

    # 5. LLM 补充判断（可选）
    if llm_client.available and not red_line:
        llm_items = _llm_check(category, pain_points, supply)
        if llm_items:
            # 去重合并（按 desc 简单去重）
            existing = {r["desc"] for r in risk_items}
            for item in llm_items:
                if item.get("desc") not in existing:
                    risk_items.append(item)
                if item.get("type") == "侵权" and item.get("level") == "高":
                    red_line = True

    return risk_items, red_line


def _llm_check(
    category: str, pain_points: list[dict[str, Any]], supply: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    review_summary = "；".join(p.get("keyword", "") for p in pain_points[:5]) or "无"
    supply_summary = (
        "；".join(f"{s.get('product_name')} 供货{s.get('supply_price')}元 MOQ{s.get('moq')}" for s in supply[:3])
        or "无"
    )
    prompt = format_prompt(
        RISK_PROMPT, category=category, review_summary=review_summary, supply_summary=supply_summary
    )
    data = llm_client.chat_json(SYSTEM_PROMPT, prompt)
    if not data:
        return []
    items = data.get("risk_items", [])
    if data.get("red_line_hit"):
        items.append({"type": "侵权", "level": "高", "desc": "LLM 判定侵权高危",
                      "mitigation": "核查专利商标，必要时放弃"})
    return items
