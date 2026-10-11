"""CLI: refresh CN daily / adj_factor / fund_flow / full_minute to local JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .dotenv import load_dotenv
from .refresh import REFRESH_DATASETS, default_refresh_dir, run_refresh
from .universe import default_universe_fixture_path


def _build_provider(args: argparse.Namespace) -> object:
    name = str(args.provider or "replay").strip().lower()
    if name == "replay":
        try:
            from stock_platform_providers import ReplayProvider, ReplayTransport
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "replay provider requires stock-platform-providers. "
                'Install with: pip install -e ".\\packages\\providers"'
            ) from exc
        fixtures = Path(args.fixtures)
        return ReplayProvider(ReplayTransport(fixtures))
    if name in {"market_db", "market_db_bulk", "engine_sqlite"}:
        try:
            from stock_platform_providers import MarketDbBulkProvider
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "market_db provider requires stock-platform-providers. "
                'Install with: pip install -e ".\\packages\\providers"'
            ) from exc
        db = str(
            args.market_db or os.environ.get("STOCK_PLATFORM_ENGINE_MARKET_DB", "") or ""
        ).strip()
        if not db:
            raise SystemExit(
                "--provider=market_db requires --market-db or "
                "STOCK_PLATFORM_ENGINE_MARKET_DB (read-only market.db path)"
            )
        return MarketDbBulkProvider(db)
    raise SystemExit(f"unsupported --provider {args.provider!r} (use replay or market_db)")


def main(argv: list[str] | None = None) -> int:
    # Load repo-root .env so CLI == .bat behaviour (P0-2).
    load_dotenv()
    p = argparse.ArgumentParser(
        description="Refresh CN panels / full_minute to local Replay-compatible JSON"
    )
    p.add_argument("--asof", required=True, help="Trade date YYYY-MM-DD")
    p.add_argument(
        "--universe",
        default=str(default_universe_fixture_path()),
        help="Universe JSON (list or {symbols: [...]})",
    )
    p.add_argument(
        "--out",
        default=None,
        help=f"Persist root (default env STOCK_PLATFORM_REFRESH_DIR or {default_refresh_dir()})",
    )
    p.add_argument(
        "--datasets",
        default=",".join(REFRESH_DATASETS),
        help="Comma list: daily,adj_factor,fund_flow,full_minute",
    )
    p.add_argument("--lookback-days", type=int, default=120)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            "P0-1: parallel workers (default 1 or STOCK_PLATFORM_REFRESH_WORKERS). "
            ">1 shares one min-interval gate so upstream rate is never exceeded"
        ),
    )
    p.add_argument(
        "--min-interval",
        type=float,
        default=None,
        help="P0-1: min seconds between upstream calls across workers (default EM_MIN_INTERVAL)",
    )
    p.add_argument(
        "--market-db",
        default=None,
        help="market.db path for --provider=market_db (default STOCK_PLATFORM_ENGINE_MARKET_DB)",
    )
    p.add_argument(
        "--provider",
        default="replay",
        help="Injected source: replay (fixtures) | market_db (offline bulk from market.db)",
    )
    p.add_argument(
        "--fixtures",
        default=None,
        help="Replay fixtures dir (required when --provider=replay)",
    )
    p.add_argument(
        "--tolerate-gaps",
        dest="tolerate_gaps",
        action="store_true",
        default=None,
        help=(
            "P0-4: treat 'no daily bars in window' as a data gap, not a failure "
            "(default: on). Gaps are reported under gaps[] and never mask real errors"
        ),
    )
    p.add_argument(
        "--no-tolerate-gaps",
        dest="tolerate_gaps",
        action="store_false",
        help="P0-4: strict mode — any symbol without daily bars fails the run (old behaviour)",
    )
    args = p.parse_args(argv)

    if args.provider == "replay" and not args.fixtures:
        p.error("--fixtures is required when --provider=replay (CI zero public net)")

    datasets = [d.strip() for d in str(args.datasets).split(",") if d.strip()]
    provider = _build_provider(args)
    asof = date.fromisoformat(args.asof)
    tolerate_gaps = args.tolerate_gaps
    if tolerate_gaps is None:
        raw = (os.environ.get("STOCK_PLATFORM_REFRESH_TOLERATE_GAPS") or "").strip().lower()
        tolerate_gaps = raw not in {"0", "false", "no", "off"}
    report = run_refresh(
        asof=asof,
        provider=provider,
        out_dir=args.out,
        universe_path=args.universe,
        datasets=datasets,
        lookback_days=args.lookback_days,
        max_attempts=args.max_attempts,
        sleeper=None,
        workers=args.workers,
        min_interval=args.min_interval,
        tolerate_gaps=bool(tolerate_gaps),
    )
    payload = report.to_dict()
    print(json.dumps({"ok": payload["ok"], "asof": payload["asof"], "failCount": payload["failCount"], "gapCount": payload["gapCount"], "outDir": payload["outDir"]}, ensure_ascii=False))
    for gap in payload["gaps"]:
        print(
            f"GAP {gap['symbol']} {gap['dataset']}: {gap['error']}",
            file=sys.stderr,
        )
    for fail in payload["failures"]:
        print(
            f"FAIL {fail['symbol']} {fail['dataset']} attempts={fail['attempts']}: {fail['error']}",
            file=sys.stderr,
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
