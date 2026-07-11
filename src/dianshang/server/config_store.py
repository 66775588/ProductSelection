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
ALLOWED_TOP = {"scoring_weights", "profit", "crawl", "api_credentials"}

# 凭证平台 → 字段列表（用于脱敏 + 校验）
CREDENTIAL_PLATFORMS: dict[str, dict[str, Any]] = {
    "1688": {
        "fields": ["alibaba_1688_app_key", "alibaba_1688_app_secret"],
        "label": "1688 开放平台",
        "doc_url": "https://open.1688.com",
        "usage": "供应链货源价格查询",
    },
    "shengyican": {
        "fields": ["sheng_yi_can_token", "sheng_yi_can_cookie"],
        "label": "生意参谋（淘宝/天猫）",
        "doc_url": "https://sycm.taobao.com",
        "usage": "市场热度、搜索趋势、转化率数据",
    },
    "jd": {
        "fields": ["jd_shangzhi_app_key", "jd_shangzhi_app_secret"],
        "label": "京东商智",
        "doc_url": "https://sz.jd.com",
        "usage": "京东平台市场数据",
    },
    "pdd": {
        "fields": ["pdd_client_id", "pdd_client_secret"],
        "label": "拼多多开放平台",
        "doc_url": "https://open.pinduoduo.com",
        "usage": "拼多多平台市场数据",
    },
}


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
    # 应用 API 凭证覆盖
    ac = overrides.get("api_credentials")
    if ac:
        cred = settings.api_credentials
        for k, v in ac.items():
            if hasattr(cred, k):
                setattr(cred, k, v)


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
        "credentials": credential_status(),
    }


# ── API 凭证管理 ──────────────────────────────────────────────


def _mask_value(value: str) -> str:
    """掩码显示：空字符串 → ''，短字符串 → '****'，长字符串 → '****' + 后 4 位"""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def validate_credentials(payload: dict[str, Any]) -> list[str]:
    """校验凭证 payload 的结构。"""
    errs: list[str] = []
    if not isinstance(payload, dict):
        return ["凭证必须是对象"]
    # 每个 key 应该是平台名
    valid_platforms = set(CREDENTIAL_PLATFORMS.keys())
    for platform_key in payload:
        if platform_key not in valid_platforms:
            errs.append(f"未知平台: {platform_key}")
            continue
        cred = payload[platform_key]
        if not isinstance(cred, dict):
            errs.append(f"{platform_key} 必须是对象")
            continue
        valid_fields = set(CREDENTIAL_PLATFORMS[platform_key]["fields"])
        for field in cred:
            if field not in valid_fields:
                errs.append(f"{platform_key}.{field} 未知字段")
    return errs


def credential_status() -> dict[str, Any]:
    """返回各平台凭证状态（脱敏），供前端展示。"""
    cred = settings.api_credentials
    result: dict[str, Any] = {}
    for platform_key, meta in CREDENTIAL_PLATFORMS.items():
        fields_masked: dict[str, str] = {}
        configured = False
        for field_name in meta["fields"]:
            raw = getattr(cred, field_name, "")
            fields_masked[field_name] = _mask_value(raw)
            if raw:
                configured = True
        result[platform_key] = {
            "label": meta["label"],
            "doc_url": meta["doc_url"],
            "usage": meta["usage"],
            "fields": fields_masked,
            "configured": configured,
        }
    return result


def save_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    """增量合并平台凭证到 runtime_overrides.json + 实时生效。"""
    errs = validate_credentials(payload)
    if errs:
        raise ValueError("; ".join(errs))

    # 展平：{ "1688": { "alibaba_1688_app_key": "x" } } → { "alibaba_1688_app_key": "x" }
    flat: dict[str, str] = {}
    for platform_key, cred in payload.items():
        for field_name, value in cred.items():
            flat[field_name] = value if value else ""

    # 透过 save_overrides 走文件锁 + 增量合并 + 实时生效
    wrapped = {"api_credentials": flat}
    merged = save_overrides(wrapped)
    cred_status = credential_status()
    # 重新读取合并后的完整凭证状态
    return credential_status()


def delete_credential(platform_key: str) -> None:
    """删除单个平台的所有凭证字段。"""
    if platform_key not in CREDENTIAL_PLATFORMS:
        raise ValueError(f"未知平台: {platform_key}")
    fields = CREDENTIAL_PLATFORMS[platform_key]["fields"]
    # 将各字段置空
    flat = {f: "" for f in fields}
    save_overrides({"api_credentials": flat})
    # 同时清空内存中的 settings
    cred = settings.api_credentials
    for f in fields:
        if hasattr(cred, f):
            setattr(cred, f, "")
