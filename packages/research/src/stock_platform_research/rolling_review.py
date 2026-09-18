"""U7 light slice: rolling recommend → review_stored_brief summary.

Uses the same ``direction_accuracy`` 口径 as U3 / performance (Buy look-long;
missing bars → pending). Does **not** invent a second win-rate metric.

Designed for offline ``engine_sqlite`` / market.db; callers must fail-closed
when no daily source is available (never silent fixtures).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Sequence

from .brief import build_premarket_brief
from .brief_review import review_stored_brief
from .universe import (
    UNIVERSE_TIERS,
    UniverseEmptyError,
    default_daily_universe_path,
    load_universe,
    normalize_universe,
    universe_size_guidance,
)

GetDaily = Callable[..., list[dict[str, Any]]]

# Soft caps so Workbench stays interactive (not full-market scan).
DEFAULT_LAST_N = 5
MAX_LAST_N = 20
DEFAULT_TOP_N = 5
MAX_SYMBOLS = 80
CALENDAR_PROBE_SYMBOL = "600519"


def _unique_trade_dates(bars: Sequence[dict[str, Any]]) -> list[date]:
    seen: set[str] = set()
    out: list[date] = []
    for b in bars:
        raw = str(b.get("date") or b.get("trade_date") or "")[:10]
        if not raw or raw in seen:
            continue
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        seen.add(raw)
        out.append(d)
    return sorted(out)


def resolve_asof_window(
    get_daily: GetDaily,
    *,
    asof_start: date | None = None,
    asof_end: date | None = None,
    last_n: int | None = None,
    probe_symbol: str = CALENDAR_PROBE_SYMBOL,
) -> list[date]:
    """Resolve inclusive signal asof dates from bars (engine calendar)."""
    n = int(last_n) if last_n is not None else None
    if n is not None:
        if n < 1:
            raise ValueError("last_n 必须 >= 1")
        if n > MAX_LAST_N:
            raise ValueError(f"last_n 上限 {MAX_LAST_N}（轻量回测；勿扫全市场长窗）")
        if asof_end is not None:
            end = asof_end
            start = end - timedelta(days=max(n * 3, 40))
            bars = get_daily([probe_symbol], start=start, end=end)
            dates = _unique_trade_dates(bars)
            return dates[-n:] if dates else []
        # Discover last available session from provider (engine coverage may lag "today").
        bars = get_daily([probe_symbol], start=date(2018, 1, 1), end=date.today())
        dates = _unique_trade_dates(bars)
        if not dates:
            return []
        return dates[-n:]

    if asof_start is None or asof_end is None:
        raise ValueError("请提供 lastN，或同时提供 asofStart 与 asofEnd")
    if asof_end < asof_start:
        raise ValueError("asofEnd 不能早于 asofStart")
    span = (asof_end - asof_start).days
    if span > 90:
        raise ValueError("asof 区间最长 90 个自然日（轻量回测）")
    bars = get_daily([probe_symbol], start=asof_start, end=asof_end)
    dates = [d for d in _unique_trade_dates(bars) if asof_start <= d <= asof_end]
    if len(dates) > MAX_LAST_N:
        raise ValueError(
            f"区间内交易日 {len(dates)} 超过上限 {MAX_LAST_N}；请缩短窗口或改用 lastN"
        )
    return dates


def resolve_universe_symbols(
    *,
    symbols: list[str] | None = None,
    universe_tier: str | None = None,
    universe_path: str | None = None,
) -> tuple[list[str], str | None, dict[str, Any]]:
    """Resolve watch/full (etc.) with soft size guidance; never silent empty."""
    tier = (universe_tier or "watch").strip().lower()
    if tier not in UNIVERSE_TIERS:
        raise UniverseEmptyError(
            f"未知宇宙层级 {universe_tier!r}；可选：{', '.join(UNIVERSE_TIERS)}"
        )
    guidance = universe_size_guidance(tier)
    if symbols is not None:
        univ = normalize_universe(symbols)
        if not univ:
            raise UniverseEmptyError("symbols 为空")
    else:
        path = universe_path or str(default_daily_universe_path())
        univ = load_universe(path, tier=tier)
    if len(univ) > MAX_SYMBOLS:
        raise UniverseEmptyError(
            f"宇宙 {len(univ)} 只超过轻量回测上限 {MAX_SYMBOLS}；"
            "请用 watch/core，或显式传入更短 symbols（勿一次全市场）"
        )
    return univ, tier, guidance


def run_rolling_recommend_review(
    *,
    get_daily: GetDaily | None,
    symbols: list[str] | None = None,
    universe_tier: str | None = "watch",
    universe_path: str | None = None,
    asof_start: date | None = None,
    asof_end: date | None = None,
    last_n: int | None = DEFAULT_LAST_N,
    holding: str = "1d",
    top_n: int = DEFAULT_TOP_N,
    soft_gates: bool = True,
    daily_source: str | None = None,
) -> dict[str, Any]:
    """Roll TopN briefs over asof dates and aggregate review_stored_brief metrics.

    When ``get_daily`` is None → fail-closed Chinese payload (HTTP layer maps to 503).
    """
    base: dict[str, Any] = {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "ok": False,
        "dailySource": daily_source,
        "holding": holding,
        "topN": int(top_n),
        "universeTier": universe_tier,
        "disclaimer": (
            "滚动推荐复盘（研究指标）；口径对齐 direction_accuracy；"
            "非投资建议；默认 SIMULATE；不冒充 live。"
        ),
    }
    if get_daily is None:
        base["error"] = (
            "无可用日线源，无法回测。请配置 STOCK_PLATFORM_ENGINE_MARKET_DB "
            "指向 a-stock-engine/data_cache/market.db（只读），或切换含 daily 的预设。"
        )
        base["failClosed"] = True
        return base

    try:
        univ, tier, guidance = resolve_universe_symbols(
            symbols=symbols,
            universe_tier=universe_tier,
            universe_path=universe_path,
        )
        asofs = resolve_asof_window(
            get_daily,
            asof_start=asof_start,
            asof_end=asof_end,
            last_n=last_n if asof_start is None else None,
        )
    except (UniverseEmptyError, ValueError) as exc:
        base["error"] = str(exc)
        base["failClosed"] = True
        return base

    if not asofs:
        base["error"] = (
            "所选区间无交易日行情（检查 engine market.db 覆盖范围或 asof / lastN）"
        )
        base["failClosed"] = True
        return base

    day_rows: list[dict[str, Any]] = []
    settled_total = 0
    pending_total = 0
    direction_hits = 0

    for asof_d in asofs:
        brief = build_premarket_brief(
            asof=asof_d,
            symbols=univ,
            daily_provider=None,
            get_daily=get_daily,
            adjust_kind=None,  # engine has no adj_factor; avoid soft-fail loops
            top_n=top_n,
            soft_gates=soft_gates,
            universe_tier=tier,
        )
        review = review_stored_brief(brief, get_daily=get_daily, holding=holding)
        settled = int(review.get("settledCount") or 0)
        pending = int(review.get("pendingCount") or 0)
        settled_total += settled
        pending_total += pending
        # Pool hits from settled Buy rows (same 口径 as review_stored_brief).
        for row in review.get("rows") or []:
            if row.get("pending"):
                continue
            if row.get("directionOk") is True:
                direction_hits += 1
        picks = brief.get("picks") or []
        day_rows.append(
            {
                "asof": asof_d.isoformat(),
                "pickCount": int(review.get("pickCount") or 0),
                "panelSize": int(brief.get("panelSize") or 0),
                "settledCount": settled,
                "pendingCount": pending,
                "directionAccuracy": review.get("directionAccuracy"),
                "gatesRelaxed": bool(brief.get("gatesRelaxed")),
                # Light payload for Workbench: click asof → 推荐区回看 / 复盘
                "pickSymbols": [
                    str(p.get("symbol") or "").strip()
                    for p in picks
                    if str(p.get("symbol") or "").strip()
                ][: int(top_n)],
            }
        )

    direction_accuracy = (direction_hits / settled_total) if settled_total else None
    return {
        **base,
        "ok": True,
        "failClosed": False,
        "universeTier": tier,
        "universeSize": len(univ),
        "universeGuidance": guidance,
        "symbols": univ,
        "asofStart": asofs[0].isoformat(),
        "asofEnd": asofs[-1].isoformat(),
        "asofCount": len(asofs),
        "lastN": last_n if asof_start is None else None,
        "settledCount": settled_total,
        "pendingCount": pending_total,
        "sampleCount": settled_total,
        "directionAccuracy": direction_accuracy,
        "direction_accuracy": direction_accuracy,
        "metricNote": (
            "direction_accuracy 与 performance / U3 复盘对齐：「看多 Buy」收益>0 算对；"
            "缺行情为 pending；不静默填 0。汇总为区间内已结算样本池化。"
        ),
        "days": day_rows,
    }
