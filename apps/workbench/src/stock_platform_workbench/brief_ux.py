"""Brief / recommend UX helpers — asof defaults, live→supplementary fallback, soft gates.

Keeps brand / vendor literals out of ``routes/`` (brand-literal CI gate).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_platform_providers import (
    ENV_TUSHARE_TOKEN,
    apply_adjust,
    get_trading_calendar,
    resolve_tushare_token,
)
from stock_platform_research import (
    UniverseEmptyError,
    build_premarket_brief,
    default_daily_universe_path,
    default_universe_fixture_path,
    load_universe,
    load_universe_tiers,
    universe_size_guidance,
)

from .paper_ux import friendly_upstream_detail, is_upstream_transport_error
from .state import CapabilityUnavailable, WorkbenchState

logger = logging.getLogger(__name__)

ENV_BRIEF_FALLBACK = "STOCK_PLATFORM_BRIEF_FALLBACK"
REPLAY_FIXTURE_ASOF = date(2026, 9, 2)
DEFAULT_DEMO_SYMBOLS = ("600519", "000001", "510300")

FALLBACK_NOTE_SUPPLEMENTARY_ZH = "已回退 Tushare（live 日线不可用）"
FALLBACK_NOTE_REPLAY_ZH = "已回退 replay fixtures（STOCK_PLATFORM_BRIEF_FALLBACK=replay）"

EMPTY_PICKS_PANEL_ZH = (
    "截面为空：所选 asof 当天无可用日线（replay 样例仅覆盖到 2026-09-02；"
    "live 请用最近交易日）。"
)
EMPTY_PICKS_GATES_ZH = (
    "入场闸门后无标的通过（样本过少或趋势/波动条件过严）。"
)
EMPTY_PICKS_TIP_ZH = (
    "可扩大 symbols（建议含 600519,000001,510300）、改用最近交易日 asof，"
    "或依赖软闸门演示模式查看按分数排序结果。"
)


def last_cn_trading_day(*, on: date | None = None) -> date:
    """Last CN trading day on or before ``on`` (default: today)."""
    cal = get_trading_calendar("CN")
    d = on or date.today()
    if cal.is_trading_day(d):
        return d
    return cal.prev_trading_day(d)


def last_completed_cn_session(*, on: date | None = None) -> date:
    """Last finished CN session for daily bars (asof for 每日选股).

    Before ~15:30 Asia/Shanghai on a trading day, today's bar is usually incomplete,
    so prefer the previous session. After close, use today.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    cal = get_trading_calendar("CN")
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz) if on is None else datetime(on.year, on.month, on.day, 16, 0, tzinfo=tz)
    d = now.date()
    if cal.is_trading_day(d) and (now.hour, now.minute) >= (15, 30):
        return d
    return cal.prev_trading_day(d)


def default_brief_asof(state: WorkbenchState) -> date:
    """Sensible default asof: last completed CN session for live; fixture for replay."""
    try:
        daily = state.resolve("daily")
    except CapabilityUnavailable:
        return last_completed_cn_session()
    name = getattr(daily, "name", "") or ""
    if name == "replay":
        return REPLAY_FIXTURE_ASOF
    return last_completed_cn_session()


def paper_now_iso_for_asof(asof: date) -> str:
    """Next calendar morning after asof (CN) for decision_only paper drafts."""
    nxt = asof + timedelta(days=1)
    return f"{nxt.isoformat()}T09:40:00+08:00"


def _default_tier_symbols(tier: str = "watch") -> list[str]:
    """Daily universe from packaged layered file (falls back to tiny demo set)."""
    key = (tier or "watch").strip().lower() or "watch"
    try:
        return load_universe(default_daily_universe_path(), tier=key)
    except Exception:  # noqa: BLE001
        return list(DEFAULT_DEMO_SYMBOLS)


def _now_shanghai_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def recommend_defaults(
    state: WorkbenchState,
    *,
    universe_tier: str | None = None,
) -> dict[str, Any]:
    asof = default_brief_asof(state)
    tier = (universe_tier or "watch").strip().lower() or "watch"
    if tier not in {"core", "watch", "full"}:
        tier = "watch"
    symbols = _default_tier_symbols(tier)
    guidance = universe_size_guidance(tier)
    try:
        tiers = load_universe_tiers(default_daily_universe_path())
        tier_sizes = {k: len(v) for k, v in tiers.items()}
    except Exception:  # noqa: BLE001
        tier_sizes = {"core": 0, "watch": len(symbols), "full": len(symbols)}
    try:
        daily = state.resolve("daily")
        provider = getattr(daily, "name", type(daily).__name__)
    except CapabilityUnavailable:
        provider = None
    live = provider not in {None, "replay"}
    tier_note = (
        f"默认 watch≈{tier_sizes.get('watch', len(symbols))} 只；"
        f"可选 full≈{tier_sizes.get('full', 0)}（更大更慢，勿一次全市场）；"
        f"core≈{tier_sizes.get('core', 0)} 最小。"
    )
    return {
        "asof": asof.isoformat(),
        "asofMode": "last_completed_cn_session" if live else "replay_fixture",
        "symbols": ",".join(symbols),
        "symbolCount": len(symbols),
        "topN": 10,
        "universeTier": tier,
        "universeTiers": ["core", "watch", "full"],
        "universeTierSizes": tier_sizes,
        "universeGuidance": guidance,
        "provider": provider,
        "softGates": True,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "generatedAt": _now_shanghai_iso(),
        "hint": (
            f"每日选股：对 {tier} 宇宙在最近完整交易日截面打分；{tier_note}"
            "可改 symbols / asof。交易始终纸面 SIMULATE。"
            if live
            else "当前为 replay 样例数据；live 请设 STOCK_PLATFORM_PROVIDER_PRESET=cn_tushare_http 并配置 TOKEN。"
        ),
        "loadingHint": (
            f"正在拉取日线并打分（{tier}≈{len(symbols)} 只），Tushare 可能需要数十秒，请稍候…"
            if live
            else "正在用 replay fixtures 生成推荐…"
        ),
    }


def _optional_resolve(state: WorkbenchState, capability: str) -> Any | None:
    try:
        return state.resolve(capability)
    except CapabilityUnavailable:
        return None


def _universe_path(state: WorkbenchState, symbols: list[str] | None) -> Path | None:
    if symbols is not None:
        return None
    daily = default_daily_universe_path()
    local_daily = Path(state.fixtures_dir) / "universe_cn_daily.json"
    if local_daily.is_file():
        return local_daily
    if daily.is_file():
        return daily
    packaged = default_universe_fixture_path()
    local = Path(state.fixtures_dir) / "universe_cn_sample.json"
    return local if local.is_file() else packaged


def _run_brief(
    *,
    state: WorkbenchState,
    asof: date,
    symbols: list[str] | None,
    top_n: int,
    value_factor: bool,
    reversal_q: float,
    adjust_kind: str | None,
    daily_provider: Any,
    soft_gates: bool,
    universe_tier: str | None = None,
) -> dict[str, Any]:
    adj = None
    adjust_fn = None
    kind = adjust_kind
    if kind:
        adj = _optional_resolve(state, "adj_factor")
        if adj is not None:
            adjust_fn = apply_adjust
        else:
            kind = None
    fund = _optional_resolve(state, "fund_flow")
    return build_premarket_brief(
        asof=asof,
        symbols=symbols,
        universe_path=_universe_path(state, symbols),
        universe_tier=universe_tier,
        daily_provider=daily_provider,
        adj_provider=adj,
        fund_flow_provider=fund,
        apply_adjust_fn=adjust_fn,
        adjust_kind=kind,
        top_n=top_n,
        value_factor=value_factor,
        reversal_q=reversal_q,
        soft_gates=soft_gates,
    )


def _fallback_daily_provider(state: WorkbenchState, primary_name: str) -> tuple[Any, str] | None:
    """Return (provider, note_zh) or None. Never silent-fake unless env asks for replay."""
    mode = (os.environ.get(ENV_BRIEF_FALLBACK) or "").strip().lower()
    if mode == "replay":
        replay = state.providers.get("replay")
        if replay is not None and primary_name != "replay":
            logger.warning("brief daily fallback → replay (%s)", ENV_BRIEF_FALLBACK)
            return replay, FALLBACK_NOTE_REPLAY_ZH
        return None

    # Explicit supplementary fallback when live HTTP dies and token is configured.
    if primary_name == "astock_http" and resolve_tushare_token():
        alt = state.providers.get("tushare_http")
        if alt is not None:
            logger.warning(
                "brief daily fallback → tushare_http (token via %s)",
                ENV_TUSHARE_TOKEN,
            )
            return alt, FALLBACK_NOTE_SUPPLEMENTARY_ZH
    return None


def _run_fallback_brief(
    state: WorkbenchState,
    *,
    primary_name: str,
    asof_d: date,
    symbols: list[str] | None,
    top_n: int,
    value_factor: bool,
    reversal_q: float,
    adjust_kind: str | None,
    soft_gates: bool,
    notes: list[str],
    universe_tier: str | None = None,
) -> dict[str, Any] | None:
    """Apply explicit fallback provider; align asof when switching to replay fixtures."""
    fb = _fallback_daily_provider(state, primary_name)
    if fb is None:
        return None
    alt, note = fb
    notes.append(note)
    asof_fb = asof_d
    if getattr(alt, "name", "") == "replay" and asof_d != REPLAY_FIXTURE_ASOF:
        asof_fb = REPLAY_FIXTURE_ASOF
        notes.append(f"asof 已对齐 replay 样例日 {REPLAY_FIXTURE_ASOF.isoformat()}")
    brief = _run_brief(
        state=state,
        asof=asof_fb,
        symbols=symbols,
        top_n=top_n,
        value_factor=value_factor,
        reversal_q=reversal_q,
        adjust_kind=adjust_kind,
        daily_provider=alt,
        soft_gates=soft_gates,
        universe_tier=universe_tier,
    )
    brief["providerFallback"] = True
    brief["providerFallbackFrom"] = primary_name
    brief["provider"] = getattr(alt, "name", type(alt).__name__)
    return brief


def build_brief_with_fallback(
    state: WorkbenchState,
    *,
    asof: date | None,
    symbols: list[str] | None,
    top_n: int = 10,
    value_factor: bool = False,
    reversal_q: float = 0.30,
    adjust_kind: str | None = "qfq",
    soft_gates: bool = True,
    universe_tier: str | None = None,
) -> dict[str, Any]:
    """Build brief using matrix daily provider; optional explicit fallback on transport/empty."""
    asof_d = asof or default_brief_asof(state)
    daily = state.resolve("daily")
    primary_name = getattr(daily, "name", type(daily).__name__)
    notes: list[str] = []
    tier = universe_tier

    # When symbols omitted, resolve tier from packaged daily universe (U6).
    if symbols is None and tier:
        try:
            symbols = _default_tier_symbols(tier)
        except Exception:  # noqa: BLE001
            symbols = None

    try:
        brief = _run_brief(
            state=state,
            asof=asof_d,
            symbols=symbols,
            top_n=top_n,
            value_factor=value_factor,
            reversal_q=reversal_q,
            adjust_kind=adjust_kind,
            daily_provider=daily,
            soft_gates=soft_gates,
            universe_tier=tier,
        )
        provider_used = primary_name
    except UniverseEmptyError:
        raise
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        if not is_upstream_transport_error(exc):
            raise
        fb_brief = _run_fallback_brief(
            state,
            primary_name=primary_name,
            asof_d=asof_d,
            symbols=symbols,
            top_n=top_n,
            value_factor=value_factor,
            reversal_q=reversal_q,
            adjust_kind=adjust_kind,
            soft_gates=soft_gates,
            notes=notes,
            universe_tier=tier,
        )
        if fb_brief is None:
            raise
        brief = fb_brief
        provider_used = brief["provider"]
    else:
        # Live/tushare returned OK but zero bars for asof — explicit offline may still help.
        if int(brief.get("panelSize") or 0) == 0 and primary_name != "replay":
            fb_brief = _run_fallback_brief(
                state,
                primary_name=primary_name,
                asof_d=asof_d,
                symbols=symbols,
                top_n=top_n,
                value_factor=value_factor,
                reversal_q=reversal_q,
                adjust_kind=adjust_kind,
                soft_gates=soft_gates,
                notes=notes,
                universe_tier=tier,
            )
            if fb_brief is not None:
                brief = fb_brief
                provider_used = brief["provider"]

    brief["provider"] = provider_used
    brief["universeTier"] = tier or brief.get("universeTier") or "watch"
    brief["generatedAt"] = _now_shanghai_iso()
    if notes:
        brief["dataNote"] = "；".join(notes)
    return brief


def friendly_brief_error(exc: BaseException) -> str:
    """Chinese detail for brief failures (no raw ConnectionError traceback)."""
    if is_upstream_transport_error(exc):
        tip = friendly_upstream_detail(exc)
        if resolve_tushare_token():
            tip += " 或已配置 STOCK_PLATFORM_TUSHARE_TOKEN 时将自动回退 Tushare。"
        tip += f" 显式离线可设 {ENV_BRIEF_FALLBACK}=replay。"
        return tip
    return f"{type(exc).__name__}: {exc}"


def ops_data_visibility() -> dict[str, Any]:
    """Preset / fallback / token flags for ops health (brand literals stay out of routes/)."""
    from stock_platform_providers import resolve_startup_preset_id

    fallback_raw = (os.environ.get(ENV_BRIEF_FALLBACK) or "").strip().lower()
    return {
        "providerPreset": resolve_startup_preset_id(),
        "briefFallback": fallback_raw if fallback_raw else None,
        # Boolean only — never echo the secret. Key avoids brand substring in routes/.
        "supplementTokenConfigured": bool(resolve_tushare_token()),
    }
