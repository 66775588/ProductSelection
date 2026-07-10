"""pytest 配置：将 src 加入路径（pyproject 已配 pythonpath，此处双保险）。"""
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 测试默认强制 Mock，避免依赖网络/Playwright
os.environ.setdefault("FORCE_MOCK", "true")
