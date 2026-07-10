"""端到端图测试：Mock 数据跑通完整流程并生成报告。"""
import os

import pytest

# conftest 已设 FORCE_MOCK=true，但 settings 在导入时已加载，运行时强制覆盖
from dianshang import config as config_module
from dianshang.agent.graph import run


@pytest.fixture(autouse=True)
def force_mock():
    config_module.settings.crawl.force_mock = True
    yield


def test_run_full_pipeline():
    state = run("保温杯", platform="pdd")
    assert state["recommendation"] in {"强烈推荐", "可尝试", "谨慎进入", "不推荐"}
    assert isinstance(state["total_score"], (int, float))
    assert "pain_points" in state
    assert "scores" in state
    # 报告至少生成 Markdown
    assert "md" in state.get("report_paths", {})
    assert os.path.exists(state["report_paths"]["md"])


def test_run_different_categories():
    a = run("保温杯")
    b = run("瑜伽垫")
    # 不同品类应产生不同得分（Mock 确定性但品类相关）
    assert a["total_score"] != b["total_score"] or a["recommendation"] != b["recommendation"]


def test_red_line_category():
    # 含禁售关键词的品类应命中红线
    state = run("电子烟")
    assert state.get("red_line_hit") is True
    assert state["recommendation"] == "不推荐"
