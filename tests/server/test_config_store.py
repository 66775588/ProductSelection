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
    keys = ["market_potential", "competition", "profit", "pain_points", "risk"]

    def writer(k):
        config_store.save_overrides(
            {"scoring_weights": {k: 0.2, **{kk: 0.2 for kk in keys if kk != k}}})

    threads = [threading.Thread(target=writer, args=(k,)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ov = config_store.load_overrides()
    assert set(ov["scoring_weights"].keys()) == set(keys)  # 五个 key 都在


def test_apply_overrides_mutates_settings():
    config_store.apply_overrides({"crawl": {"force_mock": True}})
    assert settings.crawl.force_mock is True
    config_store.apply_overrides({"crawl": {"force_mock": False}})
    assert settings.crawl.force_mock is False
