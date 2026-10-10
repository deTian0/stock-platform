"""CLI: enumerate and benchmark the whole-market universe (milestone ``X1``).

Usage::

    stock-platform-market-universe --db <market.db> --asof 2026-09-08
    stock-platform-market-universe --db <market.db> --asset-type all --json
    stock-platform-market-universe --db <market.db> --probe-panel --panel-limit 500

The numbers it prints (``elapsed_s`` / ``peak_memory_mb`` / ``counts``) are the
measured figures quoted by ``docs/ops/market-universe-benchmark.md`` — they are
produced here and nowhere else, so the doc can never quote a stale guess.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import tracemalloc
from pathlib import Path

from .market_universe import (
    ASSET_TYPE_CHOICES,
    DEFAULT_MARKET_LOOKBACK_DAYS,
    DEFAULT_MARKET_MIN_BARS,
    resolve_market_universe,
)
from .universe import UniverseEmptyError

ENV_ENGINE_MARKET_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"

MSG_NO_PROVIDERS = (
    "缺少 stock-platform-providers，无法读取 market.db：请先安装 providers 包 "
    "（pip install -e packages/providers[dev]）。"
)
MSG_NO_DB = (
    "未指定 market.db：请传 --db 指向 a-stock-engine/data_cache/market.db，"
    f"或设置环境变量 {ENV_ENGINE_MARKET_DB}。"
)


def _build_provider(db: str | None):
    try:
        from stock_platform_providers import EngineSqliteProvider  # type: ignore
    except ImportError:
        raise SystemExit(MSG_NO_PROVIDERS)
    path = str(db or os.environ.get(ENV_ENGINE_MARKET_DB, "") or "").strip()
    if not path:
        raise SystemExit(MSG_NO_DB)
    return EngineSqliteProvider(path)


def _probe_panel(provider, symbols: list[str], asof: str, lookback_days: int, limit: int | None) -> dict:
    """Build one PIT cross-section over (a slice of) the universe and measure it."""
    from .panel import build_cross_section_panel

    syms = list(symbols[: int(limit)]) if limit else list(symbols)
    tracemalloc.start()
    started = time.perf_counter()
    panel = build_cross_section_panel(
        asof=asof,
        symbols=syms,
        daily_provider=provider,
        lookback_calendar_days=int(lookback_days),
        adjust_kind=None,
    )
    elapsed = time.perf_counter() - started
    peak_bytes = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {
        "requested_symbols": len(syms),
        "panel_rows": int(len(panel)),
        "panel_columns": list(panel.columns),
        "elapsed_s": round(elapsed, 3),
        "peak_memory_mb": round(peak_bytes / (1024 * 1024), 2),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-market-universe",
        description="X1: resolve + benchmark the market-wide universe from market.db",
    )
    p.add_argument("--db", default=None, help="path to a-stock-engine data_cache/market.db")
    p.add_argument("--asof", default=None, help="YYYY-MM-DD (default: latest trade date in DB)")
    p.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_MARKET_LOOKBACK_DAYS,
        help="window length in calendar days (default 120)",
    )
    p.add_argument(
        "--min-bars",
        type=int,
        default=DEFAULT_MARKET_MIN_BARS,
        help="minimum bars inside the window to keep a code (default 1)",
    )
    p.add_argument(
        "--asset-type",
        default="stock",
        choices=list(ASSET_TYPE_CHOICES),
        help="filter by asset class (default stock)",
    )
    p.add_argument("--include-bse", action="store_true", help="keep Beijing Stock Exchange codes")
    p.add_argument("--limit", type=int, default=None, help="cap the resolved universe")
    p.add_argument("--probe-panel", action="store_true", help="also build one PIT panel and measure it")
    p.add_argument("--panel-limit", type=int, default=None, help="cap symbols used by --probe-panel")
    p.add_argument("--json", action="store_true", help="emit the full JSON payload")
    p.add_argument("--symbols-only", action="store_true", help="print one code per line")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = _build_provider(args.db)
    db_path = Path(str(provider.db_path))

    asof = args.asof or provider.latest_trade_date()
    if not asof:
        raise SystemExit(f"market.db 里没有日线数据（daily_price 为空）：{db_path}")

    try:
        universe = resolve_market_universe(
            provider,
            asof=asof,
            lookback_days=args.lookback_days,
            min_bars=args.min_bars,
            include_bse=args.include_bse,
            asset_type=args.asset_type,
            limit=args.limit,
            measure_memory=True,
        )
    except UniverseEmptyError as exc:
        print(f"FAIL {exc}")
        return 2

    if args.symbols_only:
        for code in universe.symbols:
            print(code)
        return 0

    payload = universe.to_dict()
    payload["db"] = {
        "path": str(db_path),
        "size_gb": round(db_path.stat().st_size / (1024**3), 2) if db_path.is_file() else None,
    }
    if args.probe_panel:
        payload["panel_probe"] = _probe_panel(
            provider,
            list(universe.symbols),
            asof,
            args.lookback_days,
            args.panel_limit,
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(
        "market universe: {n} codes (asset_type={at}, asof={asof}, "
        "window={win}d, min_bars={mb}, bse={bse})".format(
            n=payload["symbol_count"],
            at=payload["asset_type"],
            asof=payload["asof"],
            win=payload["lookback_days"],
            mb=payload["min_bars"],
            bse="included" if payload["include_bse"] else "excluded",
        )
    )
    print(f"  counts        : {payload['counts']}")
    print(f"  elapsed_s     : {payload['elapsed_s']}")
    print(f"  peak_memory_mb: {payload['peak_memory_mb']}")
    if "panel_probe" in payload:
        pp = payload["panel_probe"]
        print(
            "  panel probe   : {rows} rows from {req} symbols in {el}s "
            "(peak {mem} MB)".format(
                rows=pp["panel_rows"], req=pp["requested_symbols"], el=pp["elapsed_s"], mem=pp["peak_memory_mb"]
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
