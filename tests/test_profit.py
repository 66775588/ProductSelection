"""利润测算公式。"""
from dianshang.analysis.profit import calculate_profit
from dianshang.datasources.models import CompetitorProduct, SupplySource


def _make(price=50.0, supply_price=20.0, sales=500):
    comps = [
        CompetitorProduct(rank=i, title=f"p{i}", price=price, sales=sales,
                          shop_name="s", shop_level=3, sku_count=2)
        for i in range(5)
    ]
    supply = [SupplySource(product_name="货源", supply_price=supply_price, moq=10, delivery_days=2)]
    return comps, supply


def test_profit_basic_fields():
    comps, supply = _make()
    result = calculate_profit(comps, supply)
    assert "cost_breakdown" in result
    assert "合计" in result["cost_breakdown"]
    assert result["selling_price"] == 50.0
    assert result["supply_price"] == 20.0
    assert -100 < result["gross_margin"] < 100
    assert result["gross_profit"] == round(50.0 - result["cost_breakdown"]["合计"], 2)


def test_profit_high_margin_not_below_threshold():
    comps, supply = _make(price=100.0, supply_price=20.0)
    result = calculate_profit(comps, supply)
    assert result["gross_margin"] > 0
    assert result["below_threshold"] is False


def test_profit_low_margin_flagged():
    # 供货价接近售价 → 毛利为负
    comps, supply = _make(price=30.0, supply_price=28.0)
    result = calculate_profit(comps, supply)
    assert result["below_threshold"] is True
    assert result["gross_margin"] < result["threshold"]


def test_profit_empty_inputs():
    result = calculate_profit([], [])
    # 兜底默认值不报错
    assert result["selling_price"] == 50.0
    assert result["gross_margin"] is not None
