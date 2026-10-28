"""CLI for the user-readable daily digest (markdown).

Examples::

    stock-platform-digest                    # latest brief -> data/digests/latest.md
    stock-platform-digest --asof 2026-10-09  # specific day
    stock-platform-digest --out-dir D:/tmp/digests
    stock-platform-digest --no-html --no-ths # markdown only

By default this also emits the styled ``.html`` (ADR 0071) and the 同花顺
import txt (``data/ths_import/latest.txt``); ``--no-html`` / ``--no-ths`` opt out.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .daily_digest import DEFAULT_OUT_DIR, DEFAULT_THS_DIR, build_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stock-platform-digest",
        description="Render a human-readable markdown digest from the brief archive.",
    )
    parser.add_argument("--asof", default=None, help="Trade date YYYY-MM-DD; default = latest brief")
    parser.add_argument(
        "--session",
        choices=("pre", "post"),
        default=None,
        help="盘前 pre / 盘后 post。缺省读 brief payload，再缺省为 pre。不使用今天的日期",
    )
    parser.add_argument(
        "--run-date",
        default=None,
        help="任务运行日 YYYY-MM-DD。不传且 payload 也没有时，不猜测今天，行情列留空",
    )
    parser.add_argument(
        "--ohlc",
        dest="ohlc",
        action="store_true",
        default=None,
        help="取运行日外部日线。缺省：盘后开、盘前关",
    )
    parser.add_argument(
        "--no-ohlc",
        dest="ohlc",
        action="store_false",
        help="不取外部日线",
    )
    parser.set_defaults(ohlc=None)
    parser.add_argument("--out-dir", default=None, help=f"Output directory (default {DEFAULT_OUT_DIR})")
    parser.add_argument("--db-url", default=None, help="Brief SQLite URL (default STOCK_PLATFORM_DB_URL)")
    parser.add_argument("--hit-db-url", default=None, help="Hit-tracking SQLite URL (default same DB)")
    parser.add_argument(
        "--no-html",
        dest="html",
        action="store_false",
        help="Only write markdown (default: also render the styled .html alongside)",
    )
    parser.set_defaults(html=True)
    parser.add_argument(
        "--no-ths",
        dest="ths",
        action="store_false",
        help="Skip the 同花顺 import txt (default: also emit {asof}.txt + latest.txt)",
    )
    parser.add_argument(
        "--ths-dir",
        default=None,
        help=f"同花顺 import txt directory (default: a 'ths_import' sibling of --out-dir, or {DEFAULT_THS_DIR})",
    )
    parser.set_defaults(ths=True)
    args = parser.parse_args(argv)

    try:
        result = build_digest(
            asof=args.asof,
            db_url=args.db_url,
            hit_db_url=args.hit_db_url,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            emit_html=args.html,
            emit_ths=args.ths,
            ths_dir=Path(args.ths_dir) if args.ths_dir else None,
            session=args.session,
            run_date=args.run_date,
            ohlc=args.ohlc,
        )
    except Exception as exc:
        print(f"digest failed: {exc}", file=sys.stderr)
        return 1
    status = "OK" if result.get("found") else "STUB (no brief archived for this date)"
    print(f"digest {status}: asof={result['asof']} -> {result['digestPath']}")
    print(f"latest pointer: {result['latestPath']}")
    if result.get("htmlPath"):
        print(f"digest html: {result['htmlPath']} (latest: {result['latestHtmlPath']})")
    if result.get("thsPath"):
        print(f"同花顺导入·长线 ({result['thsCount']} 只): {result['thsPath']} (latest: {result['latestThsPath']})")
    if result.get("thsShortPath"):
        print(
            f"同花顺导入·短线 ({result['thsShortCount']} 只): "
            f"{result['thsShortPath']} (latest: {result['latestThsShortPath']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
