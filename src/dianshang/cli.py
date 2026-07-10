"""命令行入口（pyproject scripts: dianshang）。

用法：dianshang "保温杯" --platform pdd
"""
from __future__ import annotations

import sys

from examples.run_demo import main


def main_cli() -> None:
    sys.exit(main())


if __name__ == "__main__":
    main_cli()
