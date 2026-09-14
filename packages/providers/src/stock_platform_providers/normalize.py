"""Normalize raw vendor-shaped dicts into contract rows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .schemas import (
    DAILY_COLUMNS,
    FUND_FLOW_COLUMNS,
    LHB_INSTITUTION_COLUMNS,
    LHB_RECORD_COLUMNS,
    LHB_SEAT_COLUMNS,
    LHB_TOP_KEYS,
    REALTIME_COLUMNS,
)
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
    market: str = "CN",
) -> dict[str, Any]:
    """Map a vendor daily bar into contract fields (volume=手, amount=元)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("daily row missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

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
    market: str = "CN",
) -> dict[str, Any]:
    """Map a vendor snapshot into contract fields (ratios in decimal form)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("realtime row missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

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


def normalize_fund_flow_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Map a day-level fund-flow bar into contract fields (nets in 元)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("fund_flow row missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    trade_date = _as_date(raw.get("date") or raw.get("trade_date") or raw.get("day"))
    if trade_date is None:
        raise ValueError(f"fund_flow row for {symbol} missing date")

    row = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "date": trade_date.isoformat(),
        "main_net": _as_float(raw.get("main_net")),
        "small_net": _as_float(raw.get("small_net")),
        "mid_net": _as_float(raw.get("mid_net")),
        "large_net": _as_float(raw.get("large_net")),
        "super_net": _as_float(raw.get("super_net")),
    }
    return {k: row.get(k) for k in FUND_FLOW_COLUMNS}


def _pct_to_decimal(value: Any, *, pct_unit: str | None) -> float | None:
    n = _as_float(value)
    if n is None:
        return None
    if pct_unit == "percent":
        return n / 100.0
    return n


def _normalize_lhb_seat(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(raw.get("name") or raw.get("OPERATEDEPT_NAME") or ""),
        "buy_amt": _as_float(raw.get("buy_amt") if "buy_amt" in raw else raw.get("BUY")),
        "sell_amt": _as_float(raw.get("sell_amt") if "sell_amt" in raw else raw.get("SELL")),
        "net": _as_float(raw.get("net") if "net" in raw else raw.get("NET")),
    }


def normalize_lhb_payload(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    asof_date: date | None = None,
    look_back_days: int | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Normalize a dragon-tiger aggregate payload (amounts in 元).

    Empty ``records`` is valid (no appearance in look-back window).
    """
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("lhb payload missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    asof = _as_date(raw.get("asof_date") or raw.get("trade_date") or asof_date)
    if asof is None:
        raise ValueError(f"lhb payload for {symbol} missing asof_date")

    look_back = raw.get("look_back_days", look_back_days)
    if look_back is None:
        look_back = 30
    look_back_i = int(look_back)

    records_out: list[dict[str, Any]] = []
    for item in raw.get("records") or []:
        if not isinstance(item, dict):
            continue
        d = _as_date(item.get("date") or item.get("TRADE_DATE") or item.get("trade_date"))
        if d is None:
            continue
        pct_unit = item.get("pct_unit")
        # EM TURNOVERRATE is percent; fixtures may already be decimal.
        if "TURNOVERRATE" in item and pct_unit is None:
            pct_unit = "percent"
        elif "turnover" in item and "turnover_rate" not in item and pct_unit is None:
            pct_unit = "percent"
        turnover_raw = item.get("turnover_rate")
        if turnover_raw is None:
            turnover_raw = item.get("TURNOVERRATE", item.get("turnover"))
        rec = {
            "date": d.isoformat(),
            "reason": str(item.get("reason") or item.get("EXPLANATION") or ""),
            "net_buy": _as_float(
                item.get("net_buy") if "net_buy" in item else item.get("BILLBOARD_NET_AMT")
            ),
            "turnover_rate": _pct_to_decimal(turnover_raw, pct_unit=pct_unit),
        }
        records_out.append({k: rec.get(k) for k in LHB_RECORD_COLUMNS})

    seats_raw = raw.get("seats") or {}
    buy_seats = [_normalize_lhb_seat(s) for s in (seats_raw.get("buy") or []) if isinstance(s, dict)]
    sell_seats = [
        _normalize_lhb_seat(s) for s in (seats_raw.get("sell") or []) if isinstance(s, dict)
    ]
    seats = {
        "buy": [{k: s.get(k) for k in LHB_SEAT_COLUMNS} for s in buy_seats],
        "sell": [{k: s.get(k) for k in LHB_SEAT_COLUMNS} for s in sell_seats],
    }

    inst_raw = raw.get("institution") or {}
    buy_amt = _as_float(inst_raw.get("buy_amt")) or 0.0
    sell_amt = _as_float(inst_raw.get("sell_amt")) or 0.0
    net_amt = _as_float(inst_raw.get("net_amt"))
    if net_amt is None:
        net_amt = buy_amt - sell_amt
    institution = {
        "buy_amt": buy_amt,
        "sell_amt": sell_amt,
        "net_amt": net_amt,
    }
    institution = {k: institution.get(k) for k in LHB_INSTITUTION_COLUMNS}

    payload = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "asof_date": asof.isoformat(),
        "look_back_days": look_back_i,
        "records": records_out,
        "seats": seats,
        "institution": institution,
    }
    return {k: payload.get(k) for k in LHB_TOP_KEYS}
