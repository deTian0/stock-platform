"""CLI: entry-gate sensitivity sweep over a **read-only** engine ``market.db`` (``S3``).

    stock-platform-strategy-sensitivity --start 2023-01-01 --end 2026-09-08 \
        --knobs reversal_q,min_pick_score

Reads ``daily_price`` (code / date / close / pct_chg) from the path in
``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``), builds the shared feature frame
(:func:`backtest.prepare_book_frame`, the ``X4`` single definition) **once**, then
sweeps each requested gate knob over its grid — every point replayed through the
*same* :func:`book_replay.replay_book` loop, so two points differ only by the knob.

Prints, per knob, the grid table plus the **robust-range verdict**
(``robust`` / ``fragile`` / ``flat`` / ``insufficient``) — the ``S3`` answer to
"is the gate a plateau or a lucky single point?". SIMULATE only; off the brief /
picks path. Not investment advice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .backtest import UNIVERSES, prepare_book_frame
from .backtest_cli import ENV_DB, filter_universe, load_engine_bars
from .book_replay import ReplayParams
from .sensitivity import (
    DEFAULT_GRIDS,
    DEFAULT_OBJECTIVE,
    DEFAULT_TOLERANCE,
    OBJECTIVE_DIRECTION,
    SWEEP_KNOBS,
    build_sensitivity_report,
)


def _parse_grid(raw: str | None, knob: str) -> list[float] | None:
    if not raw:
        return None
    try:
        return [float(s) for s in raw.split(",") if s.strip()]
    except ValueError:
        raise SystemExit(f"bad grid for {knob}: {raw!r} (expected comma-separated floats)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-strategy-sensitivity",
        description="Entry-gate sensitivity sweep over a read-only market.db (SIMULATE).",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--start", default="2023-01-01", help="inclusive start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="inclusive end date YYYY-MM-DD (default: last bar)")
    p.add_argument("--universe", choices=list(UNIVERSES), default="stock", help="stock (default) | etf | all")
    p.add_argument(
        "--knobs",
        default=",".join(SWEEP_KNOBS),
        help=f"comma-separated subset of {list(SWEEP_KNOBS)} (default: all)",
    )
    p.add_argument("--objective", default=DEFAULT_OBJECTIVE, help="metric to judge robustness on (default: sharpe)")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE, help="relative plateau tolerance (default: 0.10)")
    p.add_argument("--min-pick-score", type=float, default=0.80, help="score floor held fixed when sweeping other knobs")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--reversal-q-grid", default=None, help="override grid, e.g. 0.1,0.2,0.3,0.4,0.5")
    p.add_argument("--min-pick-score-grid", default=None, help="override grid, e.g. 0.5,0.6,0.7,0.8,0.9")
    p.add_argument("--ma-band-grid", default=None, help="override grid, e.g. 0.88,0.90,0.93,0.96,0.98")
    p.add_argument("--json", action="store_true", help="emit the full report as JSON")
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

    knobs = [s.strip() for s in (args.knobs or "").split(",") if s.strip()]
    unknown = [k for k in knobs if k not in SWEEP_KNOBS]
    if unknown:
        raise SystemExit(f"unknown knob(s): {unknown}; known={list(SWEEP_KNOBS)}")

    grids: dict[str, list[float]] = {}
    for knob, raw in (
        ("reversal_q", args.reversal_q_grid),
        ("min_pick_score", args.min_pick_score_grid),
        ("ma_band", args.ma_band_grid),
    ):
        parsed = _parse_grid(raw, knob)
        if parsed is not None:
            grids[knob] = parsed

    print(f"[db] {db}", file=sys.stderr)
    bars = load_engine_bars(db, start=args.start, end=args.end)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    bars = filter_universe(bars)
    print(f"[filter] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)

    params = ReplayParams(initial_capital=args.initial_capital, max_positions=args.max_positions)
    feats = prepare_book_frame(
        bars, universe=args.universe, start=args.start, end=args.end
    )
    if feats.empty:
        print("[fail] no bars in range", file=sys.stderr)
        return 2
    n_dates = feats["trade_date"].nunique()
    print(
        f"[features] rows={len(feats)} codes={feats['code'].nunique()} dates={n_dates}",
        file=sys.stderr,
    )

    report = build_sensitivity_report(
        feats,
        knobs=knobs,
        grids=grids or None,
        objective=args.objective,
        tolerance=args.tolerance,
        min_pick_score=args.min_pick_score,
        params=params,
    )

    direction = OBJECTIVE_DIRECTION.get(args.objective, "max")
    print(
        f"=== gate sensitivity (objective={args.objective} [{direction}], "
        f"tolerance={args.tolerance:g}, dates={n_dates}) ==="
    )
    for knob in knobs:
        block = report["knobs"][knob]
        summary = block["summary"]
        print(f"\n--- {knob} ---")
        print(f"{'value':>8s} {'trades':>7s} {'sharpe':>8s} {'totRet':>9s} {'maxDD':>8s} {'calmar':>8s}")
        for pt in block["points"]:
            m = pt.get("metrics") or {}
            print(
                f"{pt['value']:>8.3f} {pt['nTrades']:>7d} "
                f"{(m.get('sharpe') if m.get('sharpe') is not None else float('nan')):>8.3f} "
                f"{(m.get('total_return') if m.get('total_return') is not None else float('nan')):>9.4f} "
                f"{(m.get('max_drawdown') if m.get('max_drawdown') is not None else float('nan')):>8.4f} "
                f"{(m.get('calmar') if m.get('calmar') is not None else float('nan')):>8.3f}"
            )
        rr = summary.get("robustRange")
        rr_txt = f"{rr['lo']}–{rr['hi']} ({rr['n']} 点)" if rr else "n/a"
        print(
            f"verdict={summary['verdict']}  best={summary.get('best')}  "
            f"robustRange={rr_txt}  stability={summary.get('stability')}  "
            f"monotonic={summary.get('monotonic')}"
        )
        print(f"  {summary['note']}")

    print(f"\noverall={report['overall']}")
    print(f"robust={report['robust']}  fragile={report['fragile']}  flat={report['flat']}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
