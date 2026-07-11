# tests/server/test_paths.py
from dianshang.server.paths import sanitize_report_path


def test_valid_filename():
    p = sanitize_report_path("bao_20260711_120000.md")
    assert p is not None
    assert p.name == "bao_20260711_120000.md"
    assert p.parent.name == "reports"


def test_parent_traversal_rejected():
    assert sanitize_report_path("../../etc/passwd") is None
    assert sanitize_report_path("../memory.db") is None


def test_absolute_path_rejected():
    assert sanitize_report_path("/etc/passwd") is None
    assert sanitize_report_path("C:/Windows/System32/drivers/etc/hosts") is None


def test_backslash_rejected():
    assert sanitize_report_path("..\\..\\secret") is None
