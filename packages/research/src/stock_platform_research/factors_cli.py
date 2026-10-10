"""CLI: factor-library IC / ICIR admission report (milestone ``S2``).

    stock-platform-factor-ic --start 2023-01-01 --end 2026-09-03 --correlation

Reads ``daily_price`` (code / date / close / pct_chg / vol / amount) **read-only**
from the path in ``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``), builds the
PIT feature frame, runs :func:`factor_ic.build_factor_ic_report` and prints each
library factor's mean IC / ICIR together with its admission verdict
(**不达标不启用**). ``--correlation`` adds the Spearman correlation matrix so
orthogonality is visible. SIMULATE only; off the brief / picks path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .backtest import UNIVERSES
from .backtest_cli import ENV_DB, filter_universe, load_engine_bars
from .factor_ic import DEFAULT_ADMISSION, build_factor_ic_report
from .factors import build_feature_frame, list_factors


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-factor-ic",
        description="Factor-library IC / ICIR admission over a read-only market.db (SIMULATE).",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--start", default="2023-01-01", help="inclusive start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="inclusive end date YYYY-MM-DD (default: last bar)")
    p.add_argument("--horizon", type=int, default=20, help="forward-return horizon in trading days")
    p.add_argument("--sample-every", type=int, default=5, help="evaluate every Nth trading day")
    p.add_argument("--min-names", type=int, default=30, help="drop cross-sections thinner than this")
    p.add_argument("--universe", choices=list(UNIVERSES), default="stock", help="stock (default) | etf | all")
    p.add_argument("--factors", default=None, help="comma-separated subset (default: whole library)")
    p.add_argument("--min-abs-ic", type=float, default=DEFAULT_ADMISSION["min_abs_ic"])
    p.add_argument("--min-abs-icir", type=float, default=DEFAULT_ADMISSION["min_abs_icir"])
    p.add_argument("--min-dates", type=int, default=int(DEFAULT_ADMISSION["min_dates"]))
    p.add_argument("--correlation", action="store_true", help="also print the factor correlation matrix")
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

    names = None
    if args.factors:
        names = [s.strip() for s in args.factors.split(",") if s.strip()]
        unknown = [n for n in names if n not in list_factors()]
        if unknown:
            raise SystemExit(f"unknown factor(s): {unknown}; known={list_factors()}")

    print(f"[db] {db}", file=sys.stderr)
    bars = load_engine_bars(db, start=args.start, end=args.end, with_amount=True)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    bars = filter_universe(bars)
    print(f"[filter] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    print(f"[universe] {args.universe}", file=sys.stderr)

    feats = build_feature_frame(bars)
    print(f"[features] rows={len(feats)}", file=sys.stderr)

    thresholds = {
        "min_abs_ic": args.min_abs_ic,
        "min_abs_icir": args.min_abs_icir,
        "min_dates": args.min_dates,
    }
    report = build_factor_ic_report(
        feats,
        horizon=args.horizon,
        factors=names,
        thresholds=thresholds,
        sample_every=args.sample_every,
        min_names=args.min_names,
    )
    if not report.get("ok"):
        print(f"[fail] {report.get('reason')}", file=sys.stderr)
        return 2

    print(f"=== factor IC/ICIR (horizon={report['horizon']}d, nDates={report['nDates']}) ===")
    print(f"{'factor':10s} {'label':16s} {'mean_ic':>9s} {'icir':>9s} {'n':>4s}  verdict")
    for name, block in report["factors"].items():
        adm = block["admission"]
        verdict = "ENABLED" if adm["passed"] else "disabled"
        ic = "n/a" if block["mean_ic"] is None else f"{block['mean_ic']:.4f}"
        icir = "n/a" if block["icir"] is None else f"{block['icir']:.4f}"
        print(f"{name:10s} {block['label']:16s} {ic:>9s} {icir:>9s} {block['n_dates'] or 0:>4d}  {verdict}")
    print(f"\nenabled={report['enabled']}")
    print(f"redundant={report['redundant']}")
    print(f"rejected={report['rejected']}")
    for name in report["rejected"] + report["redundant"]:
        print(f"  [{name}] " + "; ".join(report["factors"][name]["admission"]["reasons"]))

    corr = report.get("correlation")
    if args.correlation and corr:
        cols = list(corr)
        print("\n=== factor correlation (Spearman) ===")
        print(f"{'':12s}" + "".join(f"{c[:9]:>11s}" for c in cols))
        for row in cols:
            cells = "".join(
                ("        n/a" if corr[row][c] is None else f"{corr[row][c]:>11.3f}") for c in cols
            )
            print(f"{row[:11]:11s} " + cells)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
