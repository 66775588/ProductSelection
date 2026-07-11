# tests/test_graph_overrides.py
import os
os.environ["FORCE_MOCK"] = "true"

from dianshang.agent.graph import run
from dianshang.config import settings


def test_run_accepts_overrides_and_applies():
    state = run("保温杯", "pdd", overrides={"crawl": {"force_mock": True}})
    assert "recommendation" in state
    assert settings.crawl.force_mock is True


def test_run_backward_compatible_no_overrides():
    state = run("保温杯")
    assert "total_score" in state
