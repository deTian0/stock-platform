"""CLI: industry-neutralization A/B over a **read-only** engine ``market.db`` (``S4``).

    stock-platform-strategy-neutralization --start 2023-01-01 --end 2026-09-08 \
        --mode demean --max-per-industry 3

Reads ``daily_price`` (bars) and ``fundamentals.industry`` (the ``code → industry``
map) from the path in ``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``) — both
**read-only** — then runs the same-engine A/B
(:func:`neutralization_ab.neutralization_ab_from_bars`): arm ``raw`` vs arm
``neutral``, ``delta = neutral − raw`` plus each arm's industry-exposure profile.

SIMULATE only; off the brief / picks path. Not investment advice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .backtest import UNIVERSES
from .backtest_cli import (
    ENV_DB,
    filter_universe,
    load_engine_bars,
    load_engine_industry,
)
from .book_replay import ReplayParams
from .neutralization import NEUTRALIZE_MODES, NEUTRALIZE_RESCALES, NeutralizeParams
from .neutralization_ab import neutralization_ab_from_bars

#: metrics printed side by side (subset of ``strategy_ab.AB_METRIC_KEYS``).
_PRINT_KEYS = (
    "total_return",
    "cagr",
    "max_drawdown",
    "sharpe",
    "win_rate",
    "n_trades",
    "avg_hold_days",
    "final_equity",
)


def _fmt(v: object) -> str:
    if v is None:
        return "nan"
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return str(v)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-strategy-neutralization",
        description="Industry-neutralization A/B over a read-only market.db (SIMULATE).",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--start", default="2023-01-01", help="inclusive start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="inclusive end date YYYY-MM-DD (default: last bar)")
    p.add_argument("--universe", choices=list(UNIVERSES), default="stock", help="stock (default) | etf | all")
    p.add_argument("--mode", choices=list(NEUTRALIZE_MODES), default="demean", help="per-industry transform")
    p.add_argument("--clip", type=float, default=3.0, help="clip bound for mode=zscore (default 3.0)")
    p.add_argument("--min-group-size", type=int, default=5, help="groups smaller than this stay raw")
    p.add_argument("--rescale", choices=list(NEUTRALIZE_RESCALES), default="rank", help="post-neutralization rescale")
    p.add_argument("--no-composite-demean", action="store_true", help="skip the extra composite de-mean")
    p.add_argument("--style", default="", help="comma-separated style-exposure columns to residualize (e.g. vol20)")
    p.add_argument("--max-per-industry", type=int, default=None, help="candidate cap per industry on arm B")
    p.add_argument("--min-pick-score", type=float, default=0.80)
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
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

    style = tuple(s.strip() for s in (args.style or "").split(",") if s.strip())
    try:
        neu = NeutralizeParams(
            mode=args.mode,
            clip=args.clip,
            min_group_size=args.min_group_size,
            rescale=args.rescale,
            composite_demean=not args.no_composite_demean,
            style=style,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"[db] {db}", file=sys.stderr)
    bars = load_engine_bars(db, start=args.start, end=args.end)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    bars = filter_universe(bars)
    print(f"[filter] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    industry = load_engine_industry(db)
    print(f"[industry] codes={len(industry)}", file=sys.stderr)

    params = ReplayParams(initial_capital=args.initial_capital, max_positions=args.max_positions)
    report = neutralization_ab_from_bars(
        bars,
        neutralize=neu,
        industry_map=industry,
        universe=args.universe,
        start=args.start,
        end=args.end,
        params=params,
        max_per_industry=args.max_per_industry,
        min_pick_score=args.min_pick_score,
    )
    if not report.get("ok"):
        print(f"[fail] {report.get('reason')}", file=sys.stderr)
        return 2

    a = report["a"]
    b = report["b"]
    delta = report["delta"]
    print(
        f"=== industry neutralization A/B "
        f"(mode={neu.mode}, rescale={neu.rescale}, style={list(neu.style) or '-'}, "
        f"maxPerIndustry={args.max_per_industry}, dates={a['metrics'].get('n_days', 'n/a')}) ==="
    )
    print(f"{'metric':<24s} {'raw':>12s} {'neutral':>12s} {'delta':>12s}")
    for key in _PRINT_KEYS:
        print(
            f"{key:<24s} {_fmt((a['metrics'] or {}).get(key)):>12s} "
            f"{_fmt((b['metrics'] or {}).get(key)):>12s} {_fmt(delta.get(key)):>12s}"
        )
    print(f"\nwinner={report['winner']}  trades raw={a['tradeCount']} neutral={b['tradeCount']}")
    print(f"nIndustries={report['nIndustries']}  industryAvailable={report['industryAvailable']}")
    if report.get("warning"):
        print(f"[warn] {report['warning']}", file=sys.stderr)
    print("\n--- industry exposure (equal-weighted over each arm's picks) ---")
    for arm in ("raw", "neutral"):
        exp = report["exposure"].get(arm) or {}
        print(
            f"{arm:>8s}: codes={exp.get('n_codes')} industries={exp.get('n_industries')} "
            f"maxWeight={_fmt(exp.get('max_weight'))} ({exp.get('max_industry')}) hhi={_fmt(exp.get('hhi'))}"
        )
    if report.get("winnerNote"):
        print(f"[note] {report['winnerNote']}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
