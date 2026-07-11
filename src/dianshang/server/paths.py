# src/dianshang/server/paths.py
"""报告文件路径安全工具：锁定 data/reports 目录，防穿越。"""
from __future__ import annotations

from pathlib import Path

from dianshang.config import settings


def sanitize_report_path(filename: str) -> Path | None:
    """校验 filename 合法且 resolve 后仍在 reports_dir 内。合法返回绝对 Path。"""
    if not filename or not isinstance(filename, str):
        return None
    # 严禁穿越与绝对路径
    if "\\" in filename or "/" in filename or filename.startswith("."):
        return None
    reports_dir: Path = settings.paths.reports_dir.resolve()
    try:
        resolved = (reports_dir / filename).resolve()
    except (ValueError, OSError):
        return None
    if resolved.parent != reports_dir:
        return None
    return resolved
