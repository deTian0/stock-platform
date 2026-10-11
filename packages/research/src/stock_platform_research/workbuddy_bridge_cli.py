"""CLI: refresh the WorkBuddy MCP JSON cache from the ``westock`` CLI.

Usage::

    # default: every symbol referenced by the platform's universe config
    stock-platform-workbuddy-bridge

    # explicit symbol list / file
    stock-platform-workbuddy-bridge --symbols 600519,000001,510300
    stock-platform-workbuddy-bridge --symbols-file data/watchlist.txt

    # both datasets, 250 bars, dry run first
    stock-platform-workbuddy-bridge --datasets daily,realtime --limit 250 --dry-run

This is the write half of "workbuddy mode": it lands ``daily_{code}.json`` /
``realtime_{code}.json`` into ``STOCK_PLATFORM_WORKBUDDY_CACHE_DIR`` so the
read-only ``workbuddy`` provider has something to serve. Run it with
``STOCK_PLATFORM_PROVIDER_PRESET=workbuddy`` (see ``start-workbuddy.bat``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .dotenv import load_dotenv
from .workbuddy_bridge import (
    DEFAULT_ADJUST,
    DEFAULT_LIMIT,
    DEFAULT_PERIOD,
    ENV_WORKBUDDY_CACHE_DIR,
    load_symbols_file,
    resolve_westock_bin,
    run_bridge,
)

DATASET_CHOICES = ("daily", "realtime")


def _default_symbols() -> list[str]:
    """Fall back to the platform's own universe config (no hard-coded list)."""
    from . import universe as universe_mod

    getter = getattr(universe_mod, "load_universe_symbols", None)
    if callable(getter):  # pragma: no cover - depends on universe module shape
        try:
            return [str(s) for s in getter()]
        except Exception:  # noqa: BLE001 - never block the bridge on config shape
            return []
    return []


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-workbuddy-bridge",
        description="Populate the WorkBuddy JSON cache from the westock CLI (MCP bridge)",
    )
    p.add_argument("--symbols", default=None, help="comma-separated codes (sh600519,sz000001)")
    p.add_argument("--symbols-file", default=None, help="file with one code per line (# comments ok)")
    p.add_argument("--cache-dir", default=None, help=f"cache dir (default ${ENV_WORKBUDDY_CACHE_DIR})")
    p.add_argument("--bin", dest="binary", default=None, help="path to the westock executable")
    p.add_argument(
        "--datasets",
        default="daily",
        help="comma-separated: daily,realtime (default daily)",
    )
    p.add_argument("--period", default=DEFAULT_PERIOD, help=f"kline period (default {DEFAULT_PERIOD})")
    p.add_argument("--adjust", default=DEFAULT_ADJUST, help=f"price adjust (default {DEFAULT_ADJUST})")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"bars per symbol (default {DEFAULT_LIMIT})")
    p.add_argument("--start", default=None, help="YYYY-MM-DD (overrides --limit when given)")
    p.add_argument("--end", default=None, help="YYYY-MM-DD")
    p.add_argument("--asof", default=None, help="quote date YYYY-MM-DD (realtime only)")
    p.add_argument("--timeout", type=int, default=60, help="per-call timeout seconds (default 60)")
    p.add_argument("--dry-run", action="store_true", help="parse + report, write nothing")
    p.add_argument("--json", action="store_true", help="emit the full JSON report")
    p.add_argument("--fail-on-error", action="store_true", help="exit 1 if any symbol failed")
    return p


def _resolve_symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        syms = [s.strip() for s in str(args.symbols).split(",")]
    elif args.symbols_file:
        syms = load_symbols_file(args.symbols_file)
    else:
        syms = _default_symbols()
    return [s for s in dict.fromkeys(syms) if s]


def _resolve_datasets(raw: str) -> list[str]:
    out: list[str] = []
    for item in str(raw).split(","):
        name = item.strip().lower()
        if not name:
            continue
        if name not in DATASET_CHOICES:
            raise SystemExit(f"未知 dataset {name!r}：可选 {', '.join(DATASET_CHOICES)}")
        out.append(name)
    return out or ["daily"]


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    symbols = _resolve_symbols(args)
    if not symbols:
        print(
            "FAIL 没有可桥接的代码：请传 --symbols / --symbols-file，"
            "或配置平台宇宙（config/universe）。",
            file=sys.stderr,
        )
        return 2

    datasets = _resolve_datasets(args.datasets)

    binary = resolve_westock_bin()
    if not binary:
        print("FAIL 未找到 westock CLI。", file=sys.stderr)
        print(
            "  安装：node <finance-data-plugin>/skills/westock-data/scripts/setup.cjs "
            r"-d %USERPROFILE%\.local\bin -y",
            file=sys.stderr,
        )
        print("  或设置 STOCK_PLATFORM_WESTOCK_BIN 指向可执行文件。", file=sys.stderr)
        return 2

    report = run_bridge(
        symbols,
        cache_dir=args.cache_dir or os.environ.get(ENV_WORKBUDDY_CACHE_DIR),
        binary=binary,
        datasets=datasets,
        asof=args.asof,
        period=args.period,
        adjust=args.adjust,
        limit=args.limit,
        start=args.start,
        end=args.end,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            "workbuddy bridge: {ok}/{total} ok, {bars} bars, {fails} failed "
            "→ {d}{dry}".format(
                ok=report.ok_count,
                total=len(report.items),
                bars=report.bar_count,
                fails=len(report.failures),
                d=report.cache_dir,
                dry=" (dry-run)" if report.dry_run else "",
            )
        )
        if report.version:
            print(f"  westock    : {report.version} ({report.binary})")
        print(f"  datasets   : {', '.join(datasets)}")
        for item in report.failures:
            print(f"  FAIL {item.symbol} [{item.dataset}]: {item.error}", file=sys.stderr)
        for warning in report.warnings:
            print(f"  WARN {warning}", file=sys.stderr)

    if not report.items:
        return 2
    if args.fail_on_error and report.failures:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
