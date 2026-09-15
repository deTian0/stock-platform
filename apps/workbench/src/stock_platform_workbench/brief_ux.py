"""Brief / recommend UX helpers — asof defaults, live→supplementary fallback, soft gates.

Keeps brand / vendor literals out of ``routes/`` (brand-literal CI gate).
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from stock_platform_providers import (
    ENV_TUSHARE_TOKEN,
    apply_adjust,
    get_trading_calendar,
    resolve_tushare_token,
)
from stock_platform_research import (
    UniverseEmptyError,
    build_premarket_brief,
    default_universe_fixture_path,
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


def default_brief_asof(state: WorkbenchState) -> date:
    """Sensible default asof: last CN day for live; fixture horizon for replay."""
    try:
        daily = state.resolve("daily")
    except CapabilityUnavailable:
        return last_cn_trading_day()
    name = getattr(daily, "name", "") or ""
    if name == "replay":
        return REPLAY_FIXTURE_ASOF
    return last_cn_trading_day()


def paper_now_iso_for_asof(asof: date) -> str:
    """Next calendar morning after asof (CN) for decision_only paper drafts."""
    nxt = asof + timedelta(days=1)
    return f"{nxt.isoformat()}T09:40:00+08:00"


def recommend_defaults(state: WorkbenchState) -> dict[str, Any]:
    asof = default_brief_asof(state)
    try:
        daily = state.resolve("daily")
        provider = getattr(daily, "name", type(daily).__name__)
    except CapabilityUnavailable:
        provider = None
    return {
        "asof": asof.isoformat(),
        "symbols": ",".join(DEFAULT_DEMO_SYMBOLS),
        "topN": 5,
        "provider": provider,
        "softGates": True,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "hint": "一键「生成今日推荐」即可；asof 已按数据源选默认交易日。",
    }


def _optional_resolve(state: WorkbenchState, capability: str) -> Any | None:
    try:
        return state.resolve(capability)
    except CapabilityUnavailable:
        return None


def _universe_path(state: WorkbenchState, symbols: list[str] | None) -> Path | None:
    if symbols is not None:
        return None
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
) -> dict[str, Any]:
    """Build brief using matrix daily provider; optional explicit fallback on transport errors."""
    asof_d = asof or default_brief_asof(state)
    daily = state.resolve("daily")
    primary_name = getattr(daily, "name", type(daily).__name__)
    notes: list[str] = []

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
        )
        provider_used = primary_name
    except UniverseEmptyError:
        raise
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        if not is_upstream_transport_error(exc):
            raise
        fb = _fallback_daily_provider(state, primary_name)
        if fb is None:
            raise
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
        )
        provider_used = getattr(alt, "name", type(alt).__name__)
        brief["providerFallback"] = True
        brief["providerFallbackFrom"] = primary_name

    brief["provider"] = provider_used
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
