"""Normalize raw vendor-shaped dicts into contract rows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .schemas import DAILY_COLUMNS, REALTIME_COLUMNS
from .symbol import normalize_symbol


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        # seconds → ms heuristic
        return n * 1000 if n < 10_000_000_000 else n
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def normalize_daily_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
) -> dict[str, Any]:
    """Map a vendor daily bar into contract fields (volume=手, amount=元)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("daily row missing symbol")
    symbol = normalize_symbol(str(sym))

    open_ = _as_float(raw.get("open"))
    high = _as_float(raw.get("high"))
    low = _as_float(raw.get("low"))
    close = _as_float(raw.get("close"))
    volume = _as_float(raw.get("volume") if "volume" in raw else raw.get("vol"))
    amount = _as_float(raw.get("amount") if "amount" in raw else raw.get("amt"))
    pre_close = _as_float(raw.get("pre_close") or raw.get("prev_close"))
    change_pct = _as_float(raw.get("change_pct"))
    # percent → decimal if clearly percent-sized and flag set
    if raw.get("pct_unit") == "percent" and change_pct is not None:
        change_pct = change_pct / 100.0

    trade_date = _as_date(raw.get("date") or raw.get("trade_date") or raw.get("day"))
    if trade_date is None:
        raise ValueError(f"daily row for {symbol} missing date")

    row = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "date": trade_date.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amount,
        "pre_close": pre_close,
        "change_pct": change_pct,
        "quote_ts": _as_ms(raw.get("quote_ts") or raw.get("timestamp")),
    }
    return {k: row.get(k) for k in DAILY_COLUMNS}


def normalize_realtime_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
) -> dict[str, Any]:
    """Map a vendor snapshot into contract fields (ratios in decimal form)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("realtime row missing symbol")
    symbol = normalize_symbol(str(sym))

    change_pct = _as_float(raw.get("change_pct") or raw.get("pct"))
    amplitude = _as_float(raw.get("amplitude"))
    turnover_rate = _as_float(raw.get("turnover_rate") or raw.get("turnover"))
    if raw.get("pct_unit") == "percent":
        if change_pct is not None:
            change_pct /= 100.0
        if amplitude is not None:
            amplitude /= 100.0
        if turnover_rate is not None:
            turnover_rate /= 100.0

    asof = _as_ms(raw.get("asof_ts") or raw.get("timestamp") or raw.get("time"))
    if asof is None:
        raise ValueError(f"realtime row for {symbol} missing asof_ts")

    row = {
        "symbol": symbol,
        "name": raw.get("name"),
        "price": _as_float(raw.get("price") or raw.get("close") or raw.get("last")),
        "prev_close": _as_float(raw.get("prev_close") or raw.get("pre_close")),
        "change_amount": _as_float(raw.get("change_amount") or raw.get("change")),
        "change_pct": change_pct,
        "amplitude": amplitude,
        "turnover_rate": turnover_rate,
        "volume": _as_float(raw.get("volume") or raw.get("vol")),
        "amount": _as_float(raw.get("amount") or raw.get("amt")),
        "asof_ts": asof,
        "source": source,
        "asset_type": asset_type,
    }
    return {k: row.get(k) for k in REALTIME_COLUMNS}
