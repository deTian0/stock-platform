"""CLI: daily refresh → brief pipeline (replay-safe; optional live tushare)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .dotenv import load_dotenv
from .daily_pipeline import run_daily_pipeline
from .refresh import default_refresh_dir
from .universe import default_universe_fixture_path

# Aliases accepted by --provider / STOCK_PLATFORM_DAILY_PROVIDER
_LIVE_TUSHARE_ALIASES = frozenset({"tushare", "tushare_http", "cn_tushare_http"})
# Offline bulk source over the local warehouse (P0-1): no per-symbol HTTP.
_MARKET_DB_ALIASES = frozenset({"market_db", "market_db_bulk", "engine_sqlite"})
# WorkBuddy MCP JSON cache, populated by the bridge (stock-platform-workbuddy-bridge).
_WORKBUDDY_ALIASES = frozenset({"workbuddy", "workbuddy_mcp"})


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
    if name in _MARKET_DB_ALIASES:
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
    if name in _WORKBUDDY_ALIASES:
        try:
            from stock_platform_providers.workbuddy import (
                ENV_WORKBUDDY_CACHE_DIR,
                WorkbuddyProvider,
            )
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "workbuddy provider requires stock-platform-providers. "
                'Install with: pip install -e ".\\packages\\providers"'
            ) from exc
        cache_dir = (os.environ.get(ENV_WORKBUDDY_CACHE_DIR) or "").strip()
        if not cache_dir:
            raise SystemExit(
                "--provider=workbuddy requires STOCK_PLATFORM_WORKBUDDY_CACHE_DIR "
                "(the JSON cache the bridge writes). Run "
                "`stock-platform-workbuddy-bridge` first, or set the variable."
            )
        try:
            return WorkbuddyProvider(cache_dir)
        except FileNotFoundError as exc:
            raise SystemExit(
                f"workbuddy provider init failed: {exc} "
                "(run stock-platform-workbuddy-bridge to populate the cache)"
            ) from exc
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
        f"(use replay for CI, workbuddy for the MCP cache, market_db for the "
        f"offline warehouse, or tushare / cn_tushare_http for live daily)"
    )


def _build_market_symbol_source(args: argparse.Namespace) -> object | None:
    """X1: build the market.db symbol source when ``--universe-source=market_db``."""
    if str(args.universe_source or "config").strip().lower() != "market_db":
        return None
    try:
        from stock_platform_providers import EngineSqliteProvider
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "market_db universe requires stock-platform-providers. "
            'Install with: pip install -e ".\\packages\\providers"'
        ) from exc
    db = str(
        args.market_db or os.environ.get("STOCK_PLATFORM_ENGINE_MARKET_DB", "") or ""
    ).strip()
    if not db:
        raise SystemExit(
            "--universe-source=market_db requires --market-db or "
            "STOCK_PLATFORM_ENGINE_MARKET_DB (read-only market.db path)"
        )
    return EngineSqliteProvider(db)


def _resolve_persist(args: argparse.Namespace) -> bool:
    """Default the refresh-JSON dump by provider.

    The offline bulk source serves the whole market in one SQL pass; writing
    5.2k per-symbol JSON files (~110s) is pure overhead because the pipeline
    reads bars back through the provider and never replays the refresh dir.
    Live/replay providers keep the dump (default ``True``) so their output stays
    replayable, and an explicit flag always wins.
    """
    if args.refresh_persist is not None:
        return bool(args.refresh_persist)
    return str(args.provider or "").strip().lower() not in _MARKET_DB_ALIASES


def _resolve_tolerate_gaps(args: argparse.Namespace) -> bool:
    """P0-4: gap tolerance defaults ON, but env can pin the strict path.

    Production wants the daily run to survive a thin symbol (an ETF with a
    stale bar window) instead of failing the whole brief. CI / acceptance
    runs that assert on completeness keep the strict behaviour by exporting
    ``STOCK_PLATFORM_REFRESH_TOLERATE_GAPS=0``. An explicit flag always wins.
    """
    if args.refresh_tolerate_gaps is not None:
        return bool(args.refresh_tolerate_gaps)
    raw = (os.environ.get("STOCK_PLATFORM_REFRESH_TOLERATE_GAPS") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    # P0-2: load repo-root .env before argparse so env-derived defaults
    # (provider, token, market.db) behave the same as a .bat launch.
    load_dotenv()
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
        "--universe-source",
        default="config",
        choices=["config", "market_db"],
        help="X1: config = JSON fixture (default); market_db = whole market from market.db",
    )
    p.add_argument(
        "--market-db",
        default=None,
        help="market.db path for --universe-source=market_db (default STOCK_PLATFORM_ENGINE_MARKET_DB)",
    )
    p.add_argument(
        "--asset-type",
        default="stock",
        choices=["stock", "etf", "fund", "all"],
        help="Asset filter for --universe-source=market_db (default stock)",
    )
    p.add_argument("--min-bars", type=int, default=1, help="Min bars in window (market_db only)")
    p.add_argument("--limit", type=int, default=None, help="Cap universe size (market_db only)")
    p.add_argument("--include-bse", action="store_true", help="Keep BSE codes (market_db only)")
    p.add_argument(
        "--out",
        default=None,
        help=f"Persist root (default env STOCK_PLATFORM_REFRESH_DIR or {default_refresh_dir()})",
    )
    p.add_argument(
        "--holdings",
        default=None,
        help=(
            "X2: 持仓 JSON（list 或 {'holdings': [...]}，含 code/entry_price）"
            "→ 填充 ③A 持仓 / ③B 操作建议；不传则两榜为空（fail-closed）"
        ),
    )
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--lookback-days", type=int, default=120)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument(
        "--refresh-workers",
        type=int,
        default=None,
        help=(
            "P0-1: refresh 并发度（默认 1=串行；或 STOCK_PLATFORM_REFRESH_WORKERS）。"
            ">1 时所有 worker 共用一个最小间隔闸门，不会超过上游限速"
        ),
    )
    p.add_argument(
        "--refresh-min-interval",
        type=float,
        default=None,
        help=(
            "P0-1: 并发刷新时两次上游调用之间的最小间隔秒数"
            "（默认 EM_MIN_INTERVAL；0=不限速）"
        ),
    )
    p.add_argument(
        "--refresh-persist",
        dest="refresh_persist",
        action="store_true",
        default=None,
        help="P0-1: 强制写出每只票的 refresh JSON（默认：market_db 批量源关闭，其余开启）",
    )
    p.add_argument(
        "--no-refresh-persist",
        dest="refresh_persist",
        action="store_false",
        help="P0-1: 跳过每只票的 refresh JSON（全市场盘前推荐；省 ~110s）",
    )
    p.add_argument(
        "--refresh-tolerate-gaps",
        dest="refresh_tolerate_gaps",
        action="store_true",
        default=None,
        help=(
            "P0-4: 把「标的在窗口内无日线」当作数据缺口而非失败（默认开启）。"
            "缺口仍写入 refresh.gaps[]，不遮蔽其它真失败"
        ),
    )
    p.add_argument(
        "--no-refresh-tolerate-gaps",
        dest="refresh_tolerate_gaps",
        action="store_false",
        help=(
            "P0-4: 严格模式 —— 任一标的无日线即整轮 refresh 失败（旧行为，"
            "适合验收/取证）"
        ),
    )
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
            "Live daily: tushare / cn_tushare_http (requires STOCK_PLATFORM_TUSHARE_TOKEN). "
            "Offline bulk: market_db (whole market from market.db, single SQL pass)."
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
    p.add_argument(
        "--no-track-hits",
        action="store_true",
        help="X3: 关闭命中追踪（默认开启：②A 头部记入命中周期，落平台 SQLite）",
    )
    p.add_argument(
        "--debate-engine",
        default="off",
        choices=["off", "deterministic", "llm"],
        help=(
            "S5: 主链可选辩论车道（默认 off=零 LLM）。deterministic 无需密钥；"
            "llm 复用预算/降级（需 stock-platform-agents）"
        ),
    )
    p.add_argument(
        "--debate-max-picks",
        type=int,
        default=None,
        help="S5: 参与辩论的 picks 上限（默认全部 TopN）",
    )
    args = p.parse_args(argv)

    if args.provider == "replay" and not args.fixtures:
        p.error("--fixtures is required when --provider=replay (CI zero public net)")

    provider = _build_provider(args)
    market_source = _build_market_symbol_source(args)
    asof = date.fromisoformat(args.asof)
    holdings: list[dict[str, Any]] | None = None
    if args.holdings:
        from .position_review_cli import load_holdings  # single reader for holdings JSON

        holdings = load_holdings(args.holdings)
    debate_engine = str(args.debate_engine or "off").strip().lower()
    debate_runner = (
        _build_debate_runner()
        if debate_engine not in {"", "none", "off"}
        else None
    )
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        holdings=holdings,
        out_dir=args.out,
        universe_path=args.universe,
        universe_tier=args.tier,
        universe_source=args.universe_source,
        market_symbol_source=market_source,
        market_universe_kwargs={
            "asset_type": args.asset_type,
            "min_bars": args.min_bars,
            "limit": args.limit,
            "include_bse": bool(args.include_bse),
        },
        top_n=args.top,
        lookback_days=args.lookback_days,
        skip_refresh=bool(args.skip_refresh),
        max_attempts=args.max_attempts,
        refresh_workers=args.refresh_workers,
        refresh_min_interval=args.refresh_min_interval,
        refresh_persist=_resolve_persist(args),
        refresh_tolerate_gaps=_resolve_tolerate_gaps(args),
        track_hits=not bool(args.no_track_hits),
        debate_runner=debate_runner,
        debate_engine=debate_engine,
        debate_max_picks=args.debate_max_picks,
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
                "rankingsCounts": (payload.get("brief") or {}).get("rankingsCounts") or None,
                "hits": payload.get("hits") or None,
                "debates": payload.get("debates") or None,
                "provider": args.provider,
                "refresh": payload.get("refresh") or None,
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
    for gap in (payload.get("refresh") or {}).get("gaps") or []:
        print(
            f"GAP {gap['symbol']} {gap['dataset']}: {gap['error']}",
            file=sys.stderr,
        )
    return 0


def _build_debate_runner():
    """S5: build the injected debate runner (soft import — research stays agents-free)."""
    try:
        from stock_platform_agents import attach_debate_lane
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "--debate-engine requires stock-platform-agents. "
            'Install with: pip install -e ".\\packages\\agents"'
        ) from exc

    def _run(**kwargs: Any) -> dict[str, Any]:
        provider = kwargs.pop("provider")
        brief = kwargs.pop("brief")
        return attach_debate_lane(provider, brief, **kwargs)

    return _run


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
