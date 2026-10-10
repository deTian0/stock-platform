"""CLI: replay a **pick ledger** (or archived briefs) over a read-only ``market.db``.

    stock-platform-picks-backtest --ledger data/picks_ledger.jsonl \
        --db D:\\workspace\\stock_trading\\a-stock-engine\\data_cache\\market.db \
        --start 2026-01-01 --end 2026-10-09

    # compare the recommendations against the lvrev screener over the same bars
    stock-platform-picks-backtest --briefs-dir data/briefs --compare --json

The replay runs through ``book_replay.replay_book`` — the **same** loop the
portfolio backtest uses (``stock-platform-backtest``) — so the metric block here
and the metric block there are the same arithmetic on the same conventions. That
is the ``X4`` point: 「推荐绩效」and 「回测绩效」 no longer have two yardsticks.

Pick sources (first one wins):

* ``--ledger`` — an append-only picks JSONL (``{date, code, rank?, score?}``),
  as written by the daily pipeline / ``append_picks_ledger``
* ``--briefs-dir`` — a ``briefs/`` tree (``{asof}/brief.json`` per session); the
  ②A head of each archived brief is extracted

The DB is opened read-only (``mode=ro``) and is never written. SIMULATE only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from .backtest_cli import ENV_DB, filter_universe, load_engine_bars
from .picks_backtest import (
    compare_picks_vs_screener,
    load_picks_ledger,
    picks_from_brief,
    run_picks_backtest,
)


def load_briefs_picks(briefs_dir: str | Path) -> list[dict]:
    """Extract the ②A head from every ``{asof}/brief.json`` under ``briefs_dir``."""
    root = Path(briefs_dir)
    rows: list[dict] = []
    for path in sorted(root.glob("*/brief.json")):
        try:
            brief = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.extend(picks_from_brief(brief))
    return rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-picks-backtest",
        description="Replay a pick ledger through the shared X4 engine (SIMULATE).",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--ledger", default=None, help="picks JSONL ledger path")
    p.add_argument("--briefs-dir", default=None, help="briefs/ tree to read ②A picks from")
    p.add_argument("--start", default=None, help="inclusive start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="inclusive end date YYYY-MM-DD")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--max-picks-per-day", type=int, default=8)
    p.add_argument("--min-hold", type=int, default=45)
    p.add_argument("--stop-loss", type=float, default=8.0)
    p.add_argument(
        "--universe",
        choices=["stock", "etf", "all"],
        default="all",
        help="tradable set for the picks book (default: all — honour the pick as made)",
    )
    p.add_argument("--slippage-bps", type=float, default=0.0)
    p.add_argument(
        "--compare",
        action="store_true",
        help="also run the lvrev screener over the same bars and report the metric delta",
    )
    p.add_argument(
        "--screener-min-pick-score",
        type=float,
        default=0.0,
        help="screener score floor used only with --compare (default 0.0 = no floor)",
    )
    p.add_argument("--out", default=None, help="write the picks equity curve CSV here")
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

    if args.ledger:
        picks = load_picks_ledger(args.ledger)
        source = f"ledger:{args.ledger}"
    elif args.briefs_dir:
        picks = load_briefs_picks(args.briefs_dir)
        source = f"briefs:{args.briefs_dir}"
    else:
        raise SystemExit("no picks: pass --ledger <jsonl> or --briefs-dir <briefs/>")
    if not picks:
        raise SystemExit(f"no pick rows found in {source}")

    print(f"[db] {db}", file=sys.stderr)
    print(f"[picks] source={source} rows={len(picks)}", file=sys.stderr)
    bars = load_engine_bars(db, start=args.start, end=args.end)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    bars = filter_universe(bars)
    print(f"[filter] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)

    common = dict(
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        max_picks_per_day=args.max_picks_per_day,
        min_hold=args.min_hold,
        stop_loss=args.stop_loss,
        slippage_bps=args.slippage_bps,
        universe=args.universe,
        start=args.start,
        end=args.end,
    )

    if args.compare:
        res = compare_picks_vs_screener(
            picks,
            bars,
            picks_kwargs=common,
            screener_kwargs={**common, "universe": "stock", "min_pick_score": args.screener_min_pick_score},
        )
        print("=== picks metrics ===")
        print(json.dumps(res["picks"]["metrics"], ensure_ascii=False, indent=2))
        print("=== screener metrics ===")
        print(json.dumps(res["screener"]["metrics"], ensure_ascii=False, indent=2))
        print("=== delta (picks − screener) ===")
        print(json.dumps(res["delta"], ensure_ascii=False, indent=2))
        loop = res["picks"]
    else:
        res = run_picks_backtest(picks, bars, **common)
        loop = res
        print("=== metrics ===")
        print(json.dumps(res["metrics"], ensure_ascii=False, indent=2))

    print(
        "[replay] ok={} trades={} entered={} dropped={} outside={}".format(
            loop.get("ok"),
            len(loop.get("trades") or []),
            len(loop.get("enteredCodes") or []),
            len(loop.get("droppedPicks") or []),
            len(loop.get("picksOutsideWindow") or []),
        ),
        file=sys.stderr,
    )

    if not loop.get("ok"):
        print(f"[fail] {loop.get('reason')}", file=sys.stderr)

    if args.out:
        frame = pd.DataFrame(loop.get("equity_curve") or [])
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(out_path, index=False)
        print(f"[curve] {out_path} ({len(frame)} rows)", file=sys.stderr)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, default=str))
    return 0 if loop.get("ok") else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
