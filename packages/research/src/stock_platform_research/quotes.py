"""Run-date quotes for the digest. Network stays inside functions.

Close on the quote date comes from the external daily bar
(``day_quote_cli._fetch_ohlc`` → ``AStockHttpProvider`` / ``em_get``).

When the external source fails, the affected column is left as ``—``. The
engine ``market.db`` bar is never used as a quote (ADR 0083 §3), so there is
no engine-close fallback here.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

_OHLC_KEYS = ("open", "high", "low", "close")


def _sym6(symbol: Any) -> str:
    raw = str(symbol or "").split(".")[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    return digits.zfill(6)[-6:]


def resolve_quote_date(run_date: date) -> date:
    """Trading day of ``run_date``, or the previous one when the run day is closed."""
    from stock_platform_providers import get_trading_calendar

    calendar = get_trading_calendar("CN")
    if calendar.is_trading_day(run_date):
        return run_date
    return calendar.last_trading_day(run_date)


def resolve_prev_close(
    *,
    quote_date: str,
    asof: str,
    asof_close: float | None,
    prior_close: float | None,
) -> float | None:
    """Previous close for the self-computed return.

    When ``quote_date`` is after ``asof``, the denominator is the asof close.
    When the two dates are the same (run day fell back onto asof), the
    denominator is the engine close of the trading day *before* asof — never
    the asof close itself.
    """
    if quote_date == asof:
        if prior_close is None:
            return None
        try:
            return float(prior_close)
        except (TypeError, ValueError):
            return None
    if asof_close is None:
        return None
    try:
        return float(asof_close)
    except (TypeError, ValueError):
        return None


def _clean_bar(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _OHLC_KEYS:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:
            out[key] = number
    return out


def load_ohlc(
    symbols: list[str],
    quote_date: str,
    *,
    cache_dir: str | Path,
    allow_network: bool = True,
    fetch: Callable[[list[str], str], tuple[dict[str, Any], str | None]] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Read ``ohlc-<quote_date>.json``, fill gaps, write the same three-key shape.

    ``_fetch_ohlc`` does not touch the cache; this function does.
    A source failure with an empty cache returns ``{}`` and does not raise.
    Symbols that the external source cannot supply stay absent; callers render ``—``.
    """
    from .day_quote_cli import _cache_path, _fetch_ohlc, _read_cache

    day = str(quote_date)[:10]
    root = Path(cache_dir)
    path = _cache_path(root, day)
    cached = _read_cache(path)
    merged: dict[str, dict[str, Any]] = {}
    for key, row in cached.items():
        cleaned = _clean_bar(row)
        if cleaned:
            merged[_sym6(key)] = cleaned

    wanted = [_sym6(s) for s in symbols if _sym6(s)]
    have = {key: merged[key] for key in wanted if key in merged}
    missing = [key for key in wanted if key not in merged]
    note: str | None = None
    if missing and allow_network:
        caller = fetch or _fetch_ohlc
        try:
            fetched, err = caller(missing, day)
        except Exception as exc:  # noqa: BLE001 — external source must not break the digest
            fetched, err = {}, f"{type(exc).__name__}: {exc}"
        if err:
            note = f"外部日线不可用（{err}）"
        for key, row in (fetched or {}).items():
            cleaned = _clean_bar(row if isinstance(row, Mapping) else {})
            if cleaned:
                merged[_sym6(key)] = cleaned
                have[_sym6(key)] = cleaned
        if fetched:
            root.mkdir(parents=True, exist_ok=True)
            payload = {"asof": day, "rows": merged, "count": len(merged)}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not have and note:
        return {}, note
    if not have and missing and allow_network and note is None:
        return {}, "外部日线不可用"
    return have, note


def load_prior_closes(
    symbols: list[str],
    asof: str,
    *,
    market_db: str | None = None,
) -> dict[str, float]:
    """Engine close on the trading day before ``asof``. Empty on any failure."""
    try:
        from .dotenv import load_dotenv

        load_dotenv()  # 进程未加载 .env 时 resolve_engine_market_db() 返回 None
    except Exception:  # noqa: BLE001
        pass
    try:
        from datetime import timedelta

        from stock_platform_providers import (
            EngineSqliteProvider,
            get_trading_calendar,
            resolve_engine_market_db,
        )
    except Exception:  # noqa: BLE001
        return {}
    try:
        path = market_db or resolve_engine_market_db()
        if path is None or not Path(path).is_file():
            return {}
        day = date.fromisoformat(str(asof)[:10])
        prior = get_trading_calendar("CN").prev_trading_day(day)
        provider = EngineSqliteProvider(path)
        start = prior - timedelta(days=5)
        bars = list(provider.get_daily(list(symbols), start=start, end=prior) or [])
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, float] = {}
    for bar in bars:
        if str(bar.get("date") or "")[:10] != prior.isoformat():
            continue
        key = _sym6(bar.get("symbol"))
        close = bar.get("close")
        if key and close is not None:
            try:
                out[key] = float(close)
            except (TypeError, ValueError):
                continue
    return out


def _bars_to_intraday_last(bars: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collapse minute bars → one ``{open, high, low, close}`` per symbol.

    ``open`` = first bar open of the day; ``close`` = last bar close (现价);
    ``high`` / ``low`` = day extrema across bars. Missing fields are omitted.
    """
    by_sym: dict[str, list[Mapping[str, Any]]] = {}
    for bar in bars:
        key = _sym6(bar.get("symbol"))
        if not key:
            continue
        by_sym.setdefault(key, []).append(bar)
    out: dict[str, dict[str, Any]] = {}
    for key, rows in by_sym.items():
        ordered = sorted(rows, key=lambda r: str(r.get("datetime") or r.get("date") or ""))
        if not ordered:
            continue
        first = ordered[0]
        last = ordered[-1]
        cleaned: dict[str, Any] = {}
        try:
            cleaned["open"] = float(first.get("open"))
        except (TypeError, ValueError):
            pass
        try:
            cleaned["close"] = float(last.get("close"))
        except (TypeError, ValueError):
            pass
        highs: list[float] = []
        lows: list[float] = []
        for row in ordered:
            try:
                highs.append(float(row["high"]))
            except (TypeError, ValueError, KeyError):
                pass
            try:
                lows.append(float(row["low"]))
            except (TypeError, ValueError, KeyError):
                pass
        if highs:
            cleaned["high"] = max(highs)
        if lows:
            cleaned["low"] = min(lows)
        if cleaned.get("open") is not None or cleaned.get("close") is not None:
            out[key] = cleaned
    return out


def _default_fetch_minute(symbols: list[str], quote_date: str) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Live path: ``AStockHttpProvider.get_minute`` (em_get)."""
    try:
        from datetime import date as _date

        from stock_platform_providers.astock_http import AStockHttpProvider
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    day = _date.fromisoformat(str(quote_date)[:10])
    try:
        provider = AStockHttpProvider()
        bars = list(
            provider.get_minute(list(symbols), freq="1m", start=day, end=day) or []
        )
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    return _bars_to_intraday_last(bars), None


def load_intraday_last(
    symbols: list[str],
    quote_date: str,
    *,
    allow_network: bool = True,
    fetch: Callable[[list[str], str], tuple[dict[str, Any], str | None]] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Last-known intraday quote per symbol for midday digest (ADR 0096).

    Returns the same three-key shape as :func:`load_ohlc` (``open`` / ``high`` /
    ``low`` / ``close``), where ``close`` is the **last minute close** (现价),
    not the official daily close. Fail-soft: empty dict + note on any error.
    Does not write ``market.db``; does not invent prices.
    """
    wanted = [_sym6(s) for s in symbols if _sym6(s)]
    if not wanted:
        return {}, None
    if not allow_network and fetch is None:
        return {}, "分钟行情未取（allow_network=false）"
    caller = fetch or _default_fetch_minute
    try:
        fetched, err = caller(wanted, str(quote_date)[:10])
    except Exception as exc:  # noqa: BLE001
        return {}, f"分钟行情不可用（{type(exc).__name__}: {exc}）"
    have: dict[str, dict[str, Any]] = {}
    for key, row in (fetched or {}).items():
        cleaned = _clean_bar(row if isinstance(row, Mapping) else {})
        if cleaned:
            have[_sym6(key)] = cleaned
    if err and not have:
        return {}, f"分钟行情不可用（{err}）"
    if not have:
        return {}, err or "分钟行情不可用"
    return have, (f"分钟行情部分失败（{err}）" if err else None)


__all__ = [
    "load_intraday_last",
    "load_ohlc",
    "load_prior_closes",
    "resolve_prev_close",
    "resolve_quote_date",
]
