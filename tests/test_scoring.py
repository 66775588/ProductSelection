"""评分模型：权重计算 + 红线短路。"""
from dianshang.analysis.scoring import compute_scores


def test_red_line_short_circuits():
    result = compute_scores(
        market={"supply_demand_ratio": 3.0, "trend_30d": [{"search_index": 50}, {"search_index": 80}], "market_type": "蓝海"},
        competitors=[{"sales": 100}, {"sales": 90}, {"sales": 80}, {"sales": 70}],
        profit={"gross_margin": 60, "threshold": 30},
        pain_points=[{"keyword": "漏水", "severity": "高"}, {"keyword": "掉色", "severity": "高"}],
        risk_items=[{"type": "侵权", "level": "高", "desc": "x"}],
        red_line_hit=True,
    )
    assert result["recommendation"] == "不推荐"
    assert result["dimensions"]["risk"] == 0.0


def test_high_score_strong_recommend():
    result = compute_scores(
        market={"supply_demand_ratio": 2.5, "trend_30d": [{"search_index": 50}, {"search_index": 90}], "market_type": "蓝海"},
        competitors=[{"sales": 500}, {"sales": 400}, {"sales": 300}, {"sales": 200}, {"sales": 100}],
        profit={"gross_margin": 55, "threshold": 30},
        pain_points=[{"keyword": f"p{i}", "severity": "高"} for i in range(8)],
        risk_items=[],
        red_line_hit=False,
    )
    assert result["total_score"] >= 80
    assert result["recommendation"] == "强烈推荐"


def test_weights_sum_to_one():
    result = compute_scores(None, [], None, [], [], False)
    total_w = sum(result["weights"].values())
    assert abs(total_w - 1.0) < 1e-6


def test_low_score_not_recommended():
    result = compute_scores(
        market={"supply_demand_ratio": 0.1, "trend_30d": [{"search_index": 90}, {"search_index": 40}], "market_type": "衰退"},
        competitors=[{"sales": 50000}] * 10,  # 头部高垄断红海
        profit={"gross_margin": 5, "threshold": 30},
        pain_points=[],
        risk_items=[{"type": "侵权", "level": "高", "desc": "x"}],
        red_line_hit=False,
    )
    assert result["total_score"] < 50
    assert result["recommendation"] == "不推荐"
