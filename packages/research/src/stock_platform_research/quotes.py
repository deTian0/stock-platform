"""Run-date quotes for the digest. Network stays inside functions.

Close on the quote date comes from the external daily bar
(``day_quote_cli._fetch_ohlc`` → ``AStockHttpProvider`` / ``em_get``).

One guarded exception: when the external source is down **and** the quote date
is strictly later than the brief's ``asof`` (i.e. a session that has already
settled and been backfilled into ``market.db``), the engine close is used as a
degraded fallback so 收盘/涨跌 stay computable and 开盘 is simply absent. The
engine bar is never substituted for a same-day quote (``quote_date == asof``),
and it is never written into the external OHLC cache.
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
    selection_asof: str | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Read ``ohlc-<quote_date>.json``, fill gaps, write the same three-key shape.

    ``_fetch_ohlc`` does not touch the cache; this function does.
    A source failure with an empty cache returns ``{}`` and does not raise.

    When ``selection_asof`` is given and ``quote_date`` is **later** than it,
    symbols still missing after the external attempt get an engine-close
    fallback (:func:`load_engine_closes`) so the return/涨跌 column is never
    blank just because the HTTP source blinked. Those rows are not cached:
    the cache keeps the external (open-bearing) truth only.
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
    if selection_asof:
        gap = [key for key in wanted if key not in merged]
        try:
            later = date.fromisoformat(day) > date.fromisoformat(str(selection_asof)[:10])
        except ValueError:
            later = False
        if gap and later:
            falls_back = load_engine_closes(gap, day)
            for key, close in falls_back.items():
                merged[key] = {"close": close}
                have[key] = merged[key]
            if falls_back:
                extra = (
                    f"开盘/最高/最低不可得（外部源缺失）；"
                    f"{len(falls_back)}/{len(gap)} 只用引擎库收盘兜底，涨跌按该收盘自算"
                )
                note = f"{note}；{extra}" if note else extra
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


def load_engine_closes(
    symbols: list[str],
    day: str,
    *,
    market_db: str | None = None,
) -> dict[str, float]:
    """Engine ``market.db`` close for the single session ``day``.

    Only meaningful for a session that has already been backfilled; callers must
    gate on ``quote_date > asof`` before trusting it. Empty on any failure.
    """
    try:
        from stock_platform_providers import EngineSqliteProvider, resolve_engine_market_db
    except Exception:  # noqa: BLE001 — optional dependency surface
        return {}
    try:
        path = market_db or resolve_engine_market_db()
        if path is None or not Path(path).is_file():
            return {}
        target = date.fromisoformat(str(day)[:10])
        provider = EngineSqliteProvider(path)
        bars = list(provider.get_daily(list(symbols), start=target, end=target) or [])
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, float] = {}
    for bar in bars:
        if str(bar.get("date") or "")[:10] != target.isoformat():
            continue
        key = _sym6(bar.get("symbol"))
        close = bar.get("close")
        if not key or close is None:
            continue
        try:
            out[key] = float(close)
        except (TypeError, ValueError):
            continue
    return out


__all__ = [
    "load_engine_closes",
    "load_ohlc",
    "load_prior_closes",
    "resolve_prev_close",
    "resolve_quote_date",
]
