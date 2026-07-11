# tests/server/test_history_pagination.py
from dianshang.memory import long_term as mem


def test_history_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    for i in range(5):
        mem.save_selection({"category": f"c{i}", "platform": "pdd",
                            "recommendation": "可尝试", "total_score": 70,
                            "profit": {"gross_margin": 40}, "red_line_hit": False,
                            "report_paths": {}, "scores": {}, "pain_points": [],
                            "risk_items": []})
    page1 = mem.list_history(limit=2, offset=0)
    page2 = mem.list_history(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0]["id"] > page2[0]["id"]  # DESC


def test_history_default_backward_compatible(tmp_path, monkeypatch):
    monkeypatch.setattr(mem.settings.paths, "memory_db", tmp_path / "m.db")
    mem.init_db()
    mem.save_selection({"category": "c", "platform": "pdd", "recommendation": "可尝试",
                        "total_score": 70, "profit": {"gross_margin": 40},
                        "red_line_hit": False, "report_paths": {}, "scores": {},
                        "pain_points": [], "risk_items": []})
    rows = mem.list_history()
    assert len(rows) == 1
