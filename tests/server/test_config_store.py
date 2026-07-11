# tests/server/test_config_store.py
import threading

from dianshang.config import settings
from dianshang.server import config_store


def test_validate_rejects_bad_weights():
    errs = config_store.validate_overrides(
        {"scoring_weights": {"market_potential": 0.5, "competition": 0.2, "profit": 0.2,
                              "pain_points": 0.1, "risk": 0.1}})  # sum=1.1
    assert any("权重" in e for e in errs)


def test_validate_rejects_bad_percent_and_money():
    errs = config_store.validate_overrides({"profit": {"profit_threshold": 150.0}})
    assert errs
    errs = config_store.validate_overrides({"profit": {"packaging_cost": -1}})
    assert errs


def test_validate_rejects_unknown_key():
    errs = config_store.validate_overrides({"nope": 1})
    assert any("未知" in e for e in errs)


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "OVERRIDES_PATH", tmp_path / "ov.json")
    config_store.save_overrides({"crawl": {"force_mock": True}})
    assert config_store.load_overrides()["crawl"]["force_mock"] is True


def test_save_merges_incrementally(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "OVERRIDES_PATH", tmp_path / "ov.json")
    config_store.save_overrides({"crawl": {"force_mock": True}})
    config_store.save_overrides({"profit": {"packaging_cost": 3.0}})
    ov = config_store.load_overrides()
    assert ov["crawl"]["force_mock"] is True  # 未丢
    assert ov["profit"]["packaging_cost"] == 3.0


def test_concurrent_writes_no_loss(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "OVERRIDES_PATH", tmp_path / "ov.json")
    # 每个线程写 profit 下一个不同的子字段；只有深度合并+锁能让 7 个字段全部存活。
    # 纯 last-writer-wins（无合并）会让 profit 只剩最后一个字段 → 断言失败。
    fields = [
        ("profit_threshold", 25.0),
        ("platform_commission_rate", 0.05),
        ("logistics_rate", 0.08),
        ("promotion_rate", 0.12),
        ("refund_loss_rate", 0.04),
        ("tax_rate", 0.02),
        ("packaging_cost", 3.5),
    ]

    def writer(field, value):
        config_store.save_overrides({"profit": {field: value}})

    threads = [threading.Thread(target=writer, args=(f, v)) for f, v in fields]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ov = config_store.load_overrides()
    profit = ov["profit"]
    for f, v in fields:
        assert profit[f] == v, f"字段 {f} 丢失（说明深度合并或锁未生效）"


def test_apply_overrides_mutates_settings():
    config_store.apply_overrides({"crawl": {"force_mock": True}})
    assert settings.crawl.force_mock is True
    config_store.apply_overrides({"crawl": {"force_mock": False}})
    assert settings.crawl.force_mock is False
