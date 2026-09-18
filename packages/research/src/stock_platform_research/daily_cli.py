"""CLI: daily refresh → brief pipeline (replay-safe; optional live tushare)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .daily_pipeline import run_daily_pipeline
from .refresh import default_refresh_dir
from .universe import default_universe_fixture_path

# Aliases accepted by --provider / STOCK_PLATFORM_DAILY_PROVIDER
_LIVE_TUSHARE_ALIASES = frozenset({"tushare", "tushare_http", "cn_tushare_http"})


def _build_provider(args: argparse.Namespace) -> object:
    name = (args.provider or "replay").strip().lower()
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
    if name in _LIVE_TUSHARE_ALIASES:
        try:
            from stock_platform_providers import ENV_TUSHARE_TOKEN, TushareHttpProvider
            from stock_platform_providers.tushare_http import TushareHttpError
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "tushare provider requires stock-platform-providers. "
                'Install with: pip install -e ".\\packages\\providers"'
            ) from exc
        token = (os.environ.get(ENV_TUSHARE_TOKEN) or "").strip()
        if not token:
            raise SystemExit(
                f"live provider={name!r} requires {ENV_TUSHARE_TOKEN} "
                "(set in local .env only; never commit the token). "
                "Do not use STOCK_PLATFORM_BRIEF_FALLBACK to fake live."
            )
        try:
            return TushareHttpProvider()
        except TushareHttpError as exc:
            raise SystemExit(f"tushare provider init failed: {exc}") from exc
    raise SystemExit(
        f"unsupported --provider {args.provider!r} "
        f"(use replay for CI, or tushare / cn_tushare_http for live daily)"
    )


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
    default_provider = (os.environ.get("STOCK_PLATFORM_DAILY_PROVIDER") or "replay").strip()
    p.add_argument(
        "--provider",
        default=default_provider or "replay",
        help=(
            "Injected source. Default: replay (or STOCK_PLATFORM_DAILY_PROVIDER). "
            "Live daily: tushare / cn_tushare_http (requires STOCK_PLATFORM_TUSHARE_TOKEN)."
        ),
    )
    p.add_argument(
        "--fixtures",
        default=None,
        help="Replay fixtures dir (required when --provider=replay)",
    )
    p.add_argument(
        "--settle-after",
        action="store_true",
        help=(
            "成功后：把 brief 记入绩效 JSONL（pending）并用日线结算可结算样本 "
            "（优先 STOCK_PLATFORM_ENGINE_MARKET_DB；与 Workbench 闭环对齐）"
        ),
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
    settle_meta: dict[str, Any] = {}
    if report.ok and args.settle_after:
        settle_meta = _settle_after_pipeline(provider, report)
        payload["settleAfter"] = settle_meta
    print(
        json.dumps(
            {
                "ok": payload["ok"],
                "asof": payload["asof"],
                "stage": payload["stage"],
                "briefPath": payload.get("brief_path"),
                "provider": args.provider,
                "error": payload.get("error"),
                "settleAfter": settle_meta or None,
            },
            ensure_ascii=False,
        )
    )
    if not report.ok:
        for fail in payload.get("failures") or []:
            print(f"FAIL {fail}", file=sys.stderr)
        return 1
    return 0


def _settle_after_pipeline(provider: object, report: object) -> dict[str, Any]:
    """Log brief → performance JSONL, then settle pending with provider/engine daily."""
    from .performance import (
        default_performance_log_path,
        log_brief_decisions,
        settle_performance_log,
    )
    from .performance_cli import _build_settle_get_daily

    meta: dict[str, Any] = {
        "logged": 0,
        "settledNewly": 0,
        "ok": False,
    }
    brief_path = getattr(report, "brief_path", None) or None
    if not brief_path:
        meta["error"] = "无 brief_path，跳过 settle-after"
        return meta
    path = Path(str(brief_path))
    if not path.is_file():
        meta["error"] = f"brief 文件不存在: {path}"
        return meta
    brief = json.loads(path.read_text(encoding="utf-8"))
    log_path = default_performance_log_path()
    appended = log_brief_decisions(log_path, brief, holding="1d", skip_existing=True)
    meta["logged"] = len(appended)
    meta["logPath"] = str(log_path)

    get_daily = None
    source = None
    # Prefer engine settle path (same as CLI --settle-daily); fall back to pipeline provider.
    try:
        get_daily = _build_settle_get_daily()
        source = "settle_cli"
    except SystemExit:
        if hasattr(provider, "get_daily"):

            def _gd(symbols: list[str], *, start: date, end: date) -> list:
                return list(provider.get_daily(symbols, start=start, end=end) or [])

            get_daily = _gd
            source = getattr(provider, "name", type(provider).__name__)
    if get_daily is None:
        meta["error"] = "无日线源可结算（配置 ENGINE_MARKET_DB 或依赖 pipeline provider）"
        meta["ok"] = meta["logged"] > 0
        return meta

    summary = settle_performance_log(log_path, get_daily=get_daily)
    meta["settledNewly"] = int(summary.get("settledNewly") or 0)
    meta["settledCount"] = int(summary.get("settledCount") or 0)
    meta["pendingCount"] = int(summary.get("pendingCount") or 0)
    metrics = summary.get("metrics") or {}
    meta["direction_accuracy"] = metrics.get("direction_accuracy")
    meta["settleSource"] = source
    meta["ok"] = True
    return meta


if __name__ == "__main__":
    raise SystemExit(main())
