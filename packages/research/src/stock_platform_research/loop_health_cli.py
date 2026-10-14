"""CLI ``stock-platform-loop-health``: 日用循环健康度体检（只读 · 零网络）。

Examples::

    stock-platform-loop-health                       # 写 ./data/health/{json,md,html}
    stock-platform-loop-health --no-write            # 只打印
    stock-platform-loop-health --out-dir D:/tmp/h    # 指定输出目录
    stock-platform-loop-health --market-db D:/.../market.db --asof 2026-10-14

退出码：**0 恒成立**——体检本身不是门禁；裁决在 payload ``verdict.status`` 里
（``ok`` / ``degraded`` / ``blocked``）。需要门禁的运维脚本读 JSON 判断即可。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dotenv import load_dotenv
from .loop_health import (
    DEFAULT_LOOP_HEALTH_OUT_DIR,
    collect_loop_health,
    render_loop_health_markdown,
)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="日用循环健康度体检：聚合供数/ brief / 命中 / 绩效 / 名称（只读 · 零网络）"
    )
    p.add_argument("--db", default=None, help="平台 SQLite（默认 STOCK_PLATFORM_DB_URL）")
    p.add_argument("--market-db", default=None, help="引擎 market.db（默认环境变量）")
    p.add_argument("--perf-log", default=None,
                   help="绩效 JSONL（默认 STOCK_PLATFORM_PERFORMANCE_LOG 或 ./data/recommend_decisions.jsonl）")
    p.add_argument("--asof", default=None, help="体检时点（默认今天）")
    p.add_argument("--holding", type=int, default=5, help="持有窗口（默认 5 个交易日）")
    p.add_argument("--coverage-lookback-days", type=int, default=None,
                   help="供数覆盖率回溯窗口（默认 provider 默认 = 30）")
    p.add_argument("--coverage-min-rows", type=int, default=None,
                   help="供数覆盖率单日行数下限（默认 provider 默认 = 3000）")
    p.add_argument("--out-dir", type=Path, default=None,
                   help=f"输出目录（默认 {DEFAULT_LOOP_HEALTH_OUT_DIR}）")
    p.add_argument("--json-out", type=Path, help="覆盖 JSON 输出路径")
    p.add_argument("--out", type=Path, help="覆盖 Markdown 输出路径")
    p.add_argument("--html-out", type=Path, help="覆盖 HTML 输出路径")
    p.add_argument("--no-write", action="store_true", help="只打印，不写文件")
    args = p.parse_args(argv)

    payload = collect_loop_health(
        db_url=args.db,
        market_db=args.market_db,
        perf_log=args.perf_log,
        asof=args.asof,
        holding_days=int(args.holding),
        coverage_lookback_days=args.coverage_lookback_days,
        coverage_min_rows=args.coverage_min_rows,
    )
    md = render_loop_health_markdown(payload)

    if not args.no_write:
        out_dir = args.out_dir or Path(DEFAULT_LOOP_HEALTH_OUT_DIR)
        json_path = args.json_out or (out_dir / "loop_health.json")
        md_path = args.out or (out_dir / "loop_health.md")
        html_path = args.html_out or (out_dir / "loop_health.html")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        try:
            from .report_html import render_report_html

            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(
                render_report_html(
                    md,
                    title="日用循环健康度（loop health）",
                    badge="HEALTH",
                    generated_at=str(payload.get("generatedAt") or ""),
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — HTML 只是可选锦上添花，绝不拖垮体检
            pass

    print(md)
    verdict = payload.get("verdict") or {}
    print(
        "loop-health verdict={v} failed={f} warned={w}".format(
            v=verdict.get("status"),
            f=verdict.get("failed"),
            w=verdict.get("warned"),
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
