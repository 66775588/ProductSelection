"""运行时覆盖：校验 / 增量合并 / 文件锁持久化 / 原地应用到 settings 单例。"""
from __future__ import annotations

import json
from typing import Any

import portalocker

from dianshang.config import settings

OVERRIDES_PATH = settings.paths.data_dir / "runtime_overrides.json"

WEIGHT_KEYS = ["market_potential", "competition", "profit", "pain_points", "risk"]
PROFIT_RATE_KEYS = ["platform_commission_rate", "logistics_rate", "promotion_rate",
                    "refund_loss_rate", "tax_rate"]
ALLOWED_TOP = {"scoring_weights", "profit", "crawl"}


def validate_overrides(overrides: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(overrides, dict):
        return ["根必须是对象"]
    for key in overrides:
        if key not in ALLOWED_TOP:
            errs.append(f"未知字段: {key}")

    sw = overrides.get("scoring_weights")
    if sw is not None:
        if not isinstance(sw, dict) or set(sw.keys()) != set(WEIGHT_KEYS):
            errs.append("scoring_weights 必须包含且仅包含五个权重字段")
        elif abs(sum(sw.values()) - 1.0) > 0.01:
            errs.append(f"权重之和必须为 1.0（当前 {round(sum(sw.values()), 4)}）")

    pf = overrides.get("profit")
    if pf is not None:
        if not isinstance(pf, dict):
            errs.append("profit 必须是对象")
        else:
            if "profit_threshold" in pf and not (0 <= pf["profit_threshold"] <= 100):
                errs.append("profit_threshold 必须在 0–100")
            for k in PROFIT_RATE_KEYS:
                if k in pf and not (0 <= pf[k] <= 1):
                    errs.append(f"{k} 必须在 0–1")
            if "packaging_cost" in pf and pf["packaging_cost"] <= 0:
                errs.append("packaging_cost 必须 > 0")

    cr = overrides.get("crawl")
    if cr is not None and "force_mock" in cr and not isinstance(cr["force_mock"], bool):
        errs.append("force_mock 必须是布尔")
    return errs


def load_overrides() -> dict[str, Any]:
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        with portalocker.Lock(str(OVERRIDES_PATH), "r", timeout=5) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _deep_merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def save_overrides(merge: dict[str, Any]) -> dict[str, Any]:
    errs = validate_overrides(merge)
    if errs:
        raise ValueError("; ".join(errs))
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(str(OVERRIDES_PATH), "a+", timeout=5) as f:
        f.seek(0)
        content = f.read()
        try:
            current = json.loads(content) if content else {}
        except json.JSONDecodeError:
            current = {}
        merged = _deep_merge(current, merge)
        f.seek(0)
        f.truncate()
        json.dump(merged, f, ensure_ascii=False, indent=2)
    apply_overrides(merged)
    return merged


def apply_overrides(overrides: dict[str, Any]) -> None:
    """原地变更 settings 单例（pydantic 可变，消费方持同一引用）。"""
    sw = overrides.get("scoring_weights")
    if sw:
        for k in WEIGHT_KEYS:
            if k in sw:
                setattr(settings.scoring_weights, k, sw[k])
    pf = overrides.get("profit")
    if pf:
        for k, v in pf.items():
            if hasattr(settings.profit, k):
                setattr(settings.profit, k, v)
    cr = overrides.get("crawl")
    if cr and "force_mock" in cr:
        settings.crawl.force_mock = cr["force_mock"]


def current_config() -> dict[str, Any]:
    sw = settings.scoring_weights
    pf = settings.profit
    return {
        "scoring_weights": {k: getattr(sw, k) for k in WEIGHT_KEYS},
        "profit": {
            "profit_threshold": pf.profit_threshold,
            "platform_commission_rate": pf.platform_commission_rate,
            "logistics_rate": pf.logistics_rate,
            "promotion_rate": pf.promotion_rate,
            "refund_loss_rate": pf.refund_loss_rate,
            "tax_rate": pf.tax_rate,
            "packaging_cost": pf.packaging_cost,
        },
        "crawl": {"force_mock": settings.crawl.force_mock},
    }
