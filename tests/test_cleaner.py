"""数据清洗：去重 + 缺失标记。"""
from dianshang.datasources.models import CompetitorProduct, Dataset
from dianshang.utils.cleaner import clean_competitors, mark_missing


def _comp(title, price=50.0, sales=100):
    return CompetitorProduct(rank=1, title=title, price=price, sales=sales,
                             shop_name="s", shop_level=3, sku_count=2)


def test_dedup_by_title():
    comps = [_comp("同款A"), _comp("同款A"), _comp("同款B")]
    cleaned = clean_competitors(comps)
    assert len(cleaned) == 2


def test_mark_missing_empty_dataset():
    ds = Dataset()
    missing = mark_missing(ds)
    assert "competitors" in missing
    assert "reviews" in missing
    assert "market" in missing
    assert "supply" in missing


def test_mark_missing_complete_dataset():
    from dianshang.datasources import mock as mock_gen

    ds = Dataset(
        competitors=mock_gen.generate_competitors("x"),
        reviews=mock_gen.generate_reviews("x"),
        market=mock_gen.generate_market("x"),
        supply=mock_gen.generate_supply("x"),
    )
    assert mark_missing(ds) == {}
