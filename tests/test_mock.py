"""Mock 生成器：确定性可复现。"""
from dianshang.datasources import mock as mock_gen
from dianshang.datasources.models import DataSource


def test_mock_deterministic():
    a = mock_gen.generate_competitors("保温杯")
    b = mock_gen.generate_competitors("保温杯")
    assert len(a) == len(b) == 20
    assert [c.title for c in a] == [c.title for c in b]
    assert [c.price for c in a] == [c.price for c in b]


def test_mock_different_category_differs():
    a = mock_gen.generate_market("保温杯")
    b = mock_gen.generate_market("瑜伽垫")
    assert a.search_volume != b.search_volume or a.supply_demand_ratio != b.supply_demand_ratio


def test_mock_source_marked():
    reviews = mock_gen.generate_reviews("保温杯", n=20)
    assert all(r.source == DataSource.MOCK for r in reviews)
    # 约 40% 负面
    neg = [r for r in reviews if r.sentiment == "negative"]
    assert 2 <= len(neg) <= 14


def test_supply_price_below_competitor_median():
    comps = mock_gen.generate_competitors("保温杯")
    supply = mock_gen.generate_supply("保温杯", comps)
    median_price = sorted(c.price for c in comps)[len(comps) // 2]
    # 供货价应为中位售价的 40~55%
    for s in supply:
        assert 0.35 < s.supply_price / median_price < 0.6
