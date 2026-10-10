"""CLI: run the B1 portfolio backtest over a **read-only** engine ``market.db``.

    stock-platform-backtest --start 2020-01-01 --end 2026-09-08 --out curve.csv

Reads ``daily_price`` (code / date / close / pct_chg) from the path in
``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``), runs
``backtest.run_portfolio_backtest`` and prints a JSON metric block.

``--universe {stock|etf|all}`` selects the tradable set (milestone ``B4``);
``stock`` is the engine-aligned baseline default, ``all`` is a mixed stock + ETF
book and the metric block then carries a per-class ``by_asset`` breakdown.

The DB is opened read-only (``mode=ro``) and is never written. SIMULATE only.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from .backtest import UNIVERSES, run_portfolio_backtest
from .portfolio import DEFAULT_COMMISSION_RATE, DEFAULT_STAMP_SELL_RATE

ENV_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"


def load_engine_bars(
    db_path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    codes: list[str] | None = None,
    with_amount: bool = False,
) -> pd.DataFrame:
    """Bulk, read-only load of ``daily_price`` into a bars DataFrame.

    The engine DB holds ~8.8M rows with only ``idx_dp_date``, so a
    ``WHERE date BETWEEN ? AND ?`` clause is *slower* than a plain scan: the
    projected columns force a table walk and the index buys nothing.
    Measured 2026-10-09 on the full-period window:

    ======================================  =======
    ``... WHERE date>=? AND date<=?``        54.9 s
    ``ORDER BY date`` (hits the index)       50.6 s
    no ORDER BY, sort in pandas              52.8 s
    **plain full SELECT, filter in pandas**  **12.5 s**
    ======================================  =======

    So we always stream the whole column set and filter/sort in memory.
    """
    columns = "code, date, close, pct_chg"
    if with_amount:
        # S2 factor library needs the raw ``vol`` / ``amount``; opt-in so the
        # default column set stays byte-identical for existing callers.
        columns += ", vol, amount"
    sql = f"SELECT {columns} FROM daily_price"

    uri = "file:%s?mode=ro" % str(db_path).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        df = pd.read_sql_query(sql, con)
    finally:
        con.close()

    if start:
        df = df[df["date"] >= start]
    if end:
        df = df[df["date"] <= end]
    if codes:
        df = df[df["code"].isin(list(codes))]
    return df.sort_values(["code", "date"], ignore_index=True)


def filter_universe(df: pd.DataFrame, *, exclude_bse: bool = True) -> pd.DataFrame:
    """Drop Beijing Stock Exchange rows (``.BJ`` suffix / 4xxxxx / 8xxxxx codes)."""
    out = df
    if exclude_bse and not out.empty:
        out = out[~out["code"].str.endswith(".BJ")]
        out = out[~out["code"].str.startswith(("4", "8"))]
    return out.reset_index(drop=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-backtest",
        description="Portfolio-level backtest over a read-only engine market.db (SIMULATE).",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--start", default="2020-01-01", help="inclusive start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="inclusive end date YYYY-MM-DD (default: last bar)")
    p.add_argument("--out", default=None, help="write the equity curve CSV here")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--max-picks-per-day", type=int, default=8)
    p.add_argument("--min-hold", type=int, default=45)
    p.add_argument("--stop-loss", type=float, default=8.0)
    p.add_argument("--min-pick-score", type=float, default=0.80)
    p.add_argument(
        "--universe",
        choices=list(UNIVERSES),
        default="stock",
        help="tradable set: stock (default) | etf | all (mixed stock+ETF)",
    )
    p.add_argument(
        "--commission-rate",
        type=float,
        default=DEFAULT_COMMISSION_RATE,
        help=f"per-side commission rate (default {DEFAULT_COMMISSION_RATE:g} = 0.854/10000)",
    )
    p.add_argument(
        "--stamp-sell-rate",
        type=float,
        default=DEFAULT_STAMP_SELL_RATE,
        help=f"sell-side stamp duty, stocks only (default {DEFAULT_STAMP_SELL_RATE:g} = 5/10000)",
    )
    p.add_argument(
        "--slippage-bps",
        type=float,
        default=0.0,
        help="per-side slippage in basis points, 1 bp = 0.01%% (default: 0)",
    )
    p.add_argument(
        "--zero-cost",
        action="store_true",
        help="force commission / stamp / slippage to 0 (cost-isolation run)",
    )
    p.add_argument("--json", action="store_true", help="emit the full result as JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = (args.db or "").strip()
    if not db:
        raise SystemExit(
            f"no market.db: pass --db or set {ENV_DB} "
            "(point it at a-stock-engine/data_cache/market.db, read-only)."
        )
    if not Path(db).is_file():
        raise SystemExit(f"market.db not found: {db}")

    print(f"[db] {db}", file=sys.stderr)
    bars = load_engine_bars(db, start=args.start, end=args.end)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    bars = filter_universe(bars)
    print(f"[filter] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    print(
        "[universe] {} rows={} codes={}".format(
            args.universe, len(bars), bars["code"].nunique()
        ),
        file=sys.stderr,
    )

    commission_rate = 0.0 if args.zero_cost else args.commission_rate
    stamp_sell_rate = 0.0 if args.zero_cost else args.stamp_sell_rate
    slippage_bps = 0.0 if args.zero_cost else args.slippage_bps
    print(
        "[cost] commission={:g} stamp_sell={:g} slippage_bps={:g}".format(
            commission_rate, stamp_sell_rate, slippage_bps
        ),
        file=sys.stderr,
    )

    res = run_portfolio_backtest(
        bars,
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        max_picks_per_day=args.max_picks_per_day,
        min_hold=args.min_hold,
        stop_loss=args.stop_loss,
        min_pick_score=args.min_pick_score,
        commission_rate=commission_rate,
        stamp_sell_rate=stamp_sell_rate,
        slippage_bps=slippage_bps,
        universe=args.universe,
        start=args.start,
        end=args.end,
    )
    if not res.get("ok"):
        print(f"[fail] {res.get('reason')}", file=sys.stderr)
        return 2

    print("=== metrics ===")
    print(json.dumps(res["metrics"], ensure_ascii=False, indent=2))

    if args.out:
        curve = pd.DataFrame(res["equity_curve"])
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        curve.to_csv(out_path, index=False)
        print(f"[curve] {out_path} ({len(curve)} rows)", file=sys.stderr)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
