"""演示入口：python -m examples.run_demo "保温杯" --platform pdd

完整跑通「输入品类 → 输出选品报告」，控制台打印推荐等级与综合得分。
默认数据源走 Mock（或真实爬取失败自动回退 Mock），无需任何凭证即可运行。
"""
from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console
from rich.table import Table

from dianshang.agent.graph import run

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="电商选品调研 Agent 演示")
    parser.add_argument("category", help="目标品类，如「保温杯」")
    parser.add_argument("--platform", default="pdd", help="平台: pdd/taobao/tmall/jd")
    parser.add_argument("--verbose", action="store_true", help="打印调试日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    console.print(f"\n[bold cyan]开始选品调研：[/]品类={args.category} 平台={args.platform}\n")
    state = run(args.category, platform=args.platform)

    # 打印结论
    console.print(f"[bold]推荐等级：[/] [yellow]{state.get('recommendation')}[/]")
    console.print(f"[bold]综合得分：[/] [yellow]{state.get('total_score')}[/] / 100")
    console.print(f"[bold]判定依据：[/] {state.get('recommendation_reason')}")

    # 评分表
    table = Table(title="五维评分")
    table.add_column("维度", style="cyan")
    table.add_column("得分", style="magenta", justify="right")
    for dim, val in (state.get("scores") or {}).items():
        table.add_row(dim, str(val))
    console.print(table)

    # 痛点 TOP5
    if state.get("pain_points"):
        pp_table = Table(title="用户痛点 TOP5")
        pp_table.add_column("痛点")
        pp_table.add_column("频次", justify="right")
        pp_table.add_column("严重度")
        for p in state["pain_points"][:5]:
            pp_table.add_row(p["keyword"], str(p["frequency"]), p["severity"])
        console.print(pp_table)

    # 利润
    profit = state.get("profit") or {}
    if profit:
        console.print(
            f"\n[bold]利润测算：[/]售价 {profit.get('selling_price')}元 "
            f"毛利率 {profit.get('gross_margin')}% "
            f"回本 {profit.get('payback_months')}个月"
        )

    # 报告路径
    console.print("\n[bold green]报告已生成：[/]")
    for fmt, path in (state.get("report_paths") or {}).items():
        console.print(f"  [{fmt}] {path}")

    if state.get("errors"):
        console.print("\n[bold red]流程异常：[/]")
        for e in state["errors"]:
            console.print(f"  - {e}")


if __name__ == "__main__":
    sys.exit(main())
