"""CLI: daily refresh → brief pipeline (replay-safe)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .daily_pipeline import run_daily_pipeline
from .refresh import default_refresh_dir
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
        description="Daily pipeline: refresh → panel → premarket brief (fail-closed)"
    )
    p.add_argument("--asof", required=True, help="Trade date YYYY-MM-DD")
    p.add_argument(
        "--universe",
        default=str(default_universe_fixture_path()),
        help="Universe JSON (flat or layered core/watch/full)",
    )
    p.add_argument(
        "--tier",
        default=None,
        help="Universe tier when layered: core|watch|full (default watch for layered)",
    )
    p.add_argument(
        "--out",
        default=None,
        help=f"Persist root (default env STOCK_PLATFORM_REFRESH_DIR or {default_refresh_dir()})",
    )
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--lookback-days", type=int, default=120)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Build brief from provider only (skip refresh persist)",
    )
    p.add_argument(
        "--provider",
        default="replay",
        help="Injected source. CI/default: replay (fixtures).",
    )
    p.add_argument(
        "--fixtures",
        default=None,
        help="Replay fixtures dir (required when --provider=replay)",
    )
    args = p.parse_args(argv)

    if args.provider == "replay" and not args.fixtures:
        p.error("--fixtures is required when --provider=replay (CI zero public net)")

    provider = _build_provider(args)
    asof = date.fromisoformat(args.asof)
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=args.out,
        universe_path=args.universe,
        universe_tier=args.tier,
        top_n=args.top,
        lookback_days=args.lookback_days,
        skip_refresh=bool(args.skip_refresh),
        max_attempts=args.max_attempts,
    )
    payload = report.to_dict()
    print(
        json.dumps(
            {
                "ok": payload["ok"],
                "asof": payload["asof"],
                "stage": payload["stage"],
                "briefPath": payload.get("brief_path"),
                "error": payload.get("error"),
            },
            ensure_ascii=False,
        )
    )
    if not report.ok:
        for fail in payload.get("failures") or []:
            print(f"FAIL {fail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
