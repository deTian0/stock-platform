"""CLI: strategy A/B on the **shared** portfolio engine over a read-only ``market.db``.

    stock-platform-strategy-ab --config-a lvrev-default-v1 \
        --config-b lvrev-gate-strict-v1 --start 2020-01-01 --end 2026-09-08

Runs two versioned strategy configs through the *same* portfolio loop
(:func:`book_replay.replay_book`, the ``X4`` single definition) and prints a
side-by-side metric block + a 复盘 (review) block + ``delta = B − A``. Reads
``daily_price`` from ``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``) read-only.
SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .backtest import UNIVERSES
from .backtest_cli import filter_universe, load_engine_bars
from .book_replay import ReplayParams
from .strategy_ab import compare_strategy_ab_from_bars
from .strategy_config import default_strategy_config_dir, list_strategy_configs

ENV_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"


def _resolve(ref: str) -> str | Path:
    """Resolve a config id / packaged name / file path."""
    raw = (ref or "").strip()
    root = default_strategy_config_dir()
    candidate = root / (raw if raw.endswith(".json") else f"{raw}.json")
    if candidate.is_file():
        return candidate
    path = Path(raw)
    if path.is_file():
        return path
    for cfg in list_strategy_configs():
        if str(cfg.get("id")) == raw:
            return str(cfg.get("path"))
    raise SystemExit(f"strategy config not found: {ref}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-strategy-ab",
        description="Strategy A/B on the shared portfolio engine (SIMULATE).",
    )
    p.add_argument(
        "--db",
        default=os.environ.get(ENV_DB, ""),
        help=f"market.db path (default: ${ENV_DB})",
    )
    p.add_argument("--config-a", default="lvrev-default-v1", help="config A id or JSON path")
    p.add_argument(
        "--config-b", default="lvrev-rev-heavy-v1", help="config B id or JSON path"
    )
    p.add_argument("--start", default="2020-01-01", help="inclusive start YYYY-MM-DD")
    p.add_argument("--end", default=None, help="inclusive end YYYY-MM-DD (default: last bar)")
    p.add_argument(
        "--universe",
        choices=list(UNIVERSES),
        default="stock",
        help="tradable set: stock (default) | etf | all",
    )
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
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

    cfg_a = _resolve(args.config_a)
    cfg_b = _resolve(args.config_b)

    print(f"[db] {db}", file=sys.stderr)
    bars = load_engine_bars(db, start=args.start, end=args.end)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    bars = filter_universe(bars)
    print(
        "[universe] {} rows={} codes={}".format(
            args.universe, len(bars), bars["code"].nunique()
        ),
        file=sys.stderr,
    )

    res = compare_strategy_ab_from_bars(
        bars,
        cfg_a,
        cfg_b,
        universe=args.universe,
        start=args.start,
        end=args.end,
        params=ReplayParams(
            initial_capital=args.initial_capital, max_positions=args.max_positions
        ),
    )
    if not res.get("ok"):
        print(f"[fail] {res.get('reason')}", file=sys.stderr)
        return 2

    a = res.get("a") or {}
    b = res.get("b") or {}
    print(
        f"winner={res.get('winner')}  universe={res.get('universe')}  "
        f"A={a.get('configId')}  B={b.get('configId')}"
    )
    print("=== metrics ===")
    print(
        json.dumps(
            {"A": a.get("metrics"), "B": b.get("metrics"), "delta": res.get("delta")},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("=== review (复盘) ===")
    print(json.dumps({"A": a.get("review"), "B": b.get("review")}, ensure_ascii=False, indent=2))
    if args.json:
        print(json.dumps(res, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
