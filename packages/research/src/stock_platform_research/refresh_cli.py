"""CLI: refresh CN daily / adj_factor / fund_flow / full_minute to local JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .refresh import REFRESH_DATASETS, default_refresh_dir, run_refresh
from .universe import default_universe_fixture_path


def _build_provider(args: argparse.Namespace) -> object:
    if args.provider == "replay":
        try:
            from stock_platform_providers import ReplayProvider, ReplayTransport
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "replay provider requires stock-platform-providers. "
                'Install with: pip install -e ".\\packages\\providers"'
            ) from exc
        fixtures = Path(args.fixtures)
        return ReplayProvider(ReplayTransport(fixtures))
    raise SystemExit(f"unsupported --provider {args.provider!r} (use replay in CI)")


def main(argv: list[str] | None = None) -> int:
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
        "--provider",
        default="replay",
        help="Injected source name. CI/default: replay (fixtures). Live is opt-in elsewhere.",
    )
    p.add_argument(
        "--fixtures",
        default=None,
        help="Replay fixtures dir (required when --provider=replay)",
    )
    args = p.parse_args(argv)

    if args.provider == "replay" and not args.fixtures:
        p.error("--fixtures is required when --provider=replay (CI zero public net)")

    datasets = [d.strip() for d in str(args.datasets).split(",") if d.strip()]
    provider = _build_provider(args)
    asof = date.fromisoformat(args.asof)
    report = run_refresh(
        asof=asof,
        provider=provider,
        out_dir=args.out,
        universe_path=args.universe,
        datasets=datasets,
        lookback_days=args.lookback_days,
        max_attempts=args.max_attempts,
        sleeper=None,
    )
    payload = report.to_dict()
    print(json.dumps({"ok": payload["ok"], "asof": payload["asof"], "failCount": payload["failCount"], "outDir": payload["outDir"]}, ensure_ascii=False))
    for fail in payload["failures"]:
        print(
            f"FAIL {fail['symbol']} {fail['dataset']} attempts={fail['attempts']}: {fail['error']}",
            file=sys.stderr,
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
