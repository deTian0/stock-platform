"""Normalize raw vendor-shaped dicts into contract rows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .schemas import (
    ADJ_FACTOR_COLUMNS,
    ADJ_FACTOR_KINDS,
    CONCEPT_BLOCK_COLUMNS,
    CONCEPT_BLOCKS_TOP_KEYS,
    DAILY_COLUMNS,
    DEPTH5_COLUMNS,
    DEPTH5_LEVELS,
    FINANCIAL_BALANCE_COLUMNS,
    FINANCIAL_CASHFLOW_COLUMNS,
    FINANCIAL_INCOME_COLUMNS,
    FINANCIAL_TOP_KEYS,
    FUND_FLOW_COLUMNS,
    LHB_INSTITUTION_COLUMNS,
    LHB_RECORD_COLUMNS,
    LHB_SEAT_COLUMNS,
    LHB_TOP_KEYS,
    MINUTE_COLUMNS,
    MINUTE_FREQS,
    NEWS_COLUMNS,
    REALTIME_COLUMNS,
    SECTOR_FUND_FLOW_COLUMNS,
    UNLOCK_EVENT_COLUMNS,
    UNLOCK_TOP_KEYS,
)
from .symbol import normalize_sector_code, normalize_symbol


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


def _as_beijing_naive_datetime(value: Any) -> str | None:
    """Normalize to ``YYYY-MM-DD HH:MM:SS`` Beijing wall clock (no tz suffix).

    Rejects timezone-aware inputs and ``Z`` / offset suffixes — minute bars must
    not be stored as UTC.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise ValueError("minute datetime must be Beijing wall-clock naive (no tz)")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if text.endswith("Z") or "+" in text[10:] or text.endswith("UTC"):
        raise ValueError(f"minute datetime must not carry timezone: {text!r}")
    # Accept "YYYY-MM-DD HH:MM" / "YYYY-MM-DDTHH:MM:SS" / with seconds
    text = text.replace("T", " ")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid minute datetime: {text!r}") from exc
    if dt.tzinfo is not None:
        raise ValueError("minute datetime must be Beijing wall-clock naive (no tz)")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def normalize_minute_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    default_freq: str = "1m",
    market: str = "CN",
) -> dict[str, Any]:
    """Map a vendor minute bar into contract fields (volume=手, amount=元)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("minute row missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    freq = str(raw.get("freq") or default_freq).strip().lower()
    if freq.isdigit():
        freq = f"{freq}m"
    if freq not in MINUTE_FREQS:
        raise ValueError(f"minute freq must be one of {sorted(MINUTE_FREQS)}, got {freq!r}")

    dt = _as_beijing_naive_datetime(
        raw.get("datetime") or raw.get("time") or raw.get("date") or raw.get("dt")
    )
    if dt is None:
        raise ValueError(f"minute row for {symbol} missing datetime")

    row = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "datetime": dt,
        "open": _as_float(raw.get("open")),
        "high": _as_float(raw.get("high")),
        "low": _as_float(raw.get("low")),
        "close": _as_float(raw.get("close")),
        "volume": _as_float(raw.get("volume") if "volume" in raw else raw.get("vol")),
        "amount": _as_float(raw.get("amount") if "amount" in raw else raw.get("amt")),
        "freq": freq,
    }
    return {k: row.get(k) for k in MINUTE_COLUMNS}


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


def normalize_sector_fund_flow_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "sector",
    default_sector_code: str | None = None,
) -> dict[str, Any]:
    """Map a board/sector day-level fund-flow bar (nets in 元)."""
    if asset_type not in {"sector", "index"}:
        raise ValueError(
            f"sector_fund_flow asset_type must be 'sector' or 'index', got {asset_type!r}"
        )
    code_raw = (
        raw.get("sector_code")
        or raw.get("code")
        or raw.get("board_code")
        or default_sector_code
    )
    if not code_raw:
        raise ValueError("sector_fund_flow row missing sector_code")
    sector_code = normalize_sector_code(str(code_raw))

    trade_date = _as_date(raw.get("date") or raw.get("trade_date") or raw.get("day"))
    if trade_date is None:
        raise ValueError(f"sector_fund_flow row for {sector_code} missing date")

    name = raw.get("sector_name") or raw.get("name") or raw.get("board_name")
    sector_name = str(name).strip() if name not in (None, "") else None

    row = {
        "sector_code": sector_code,
        "sector_name": sector_name,
        "asset_type": asset_type,
        "source": source,
        "date": trade_date.isoformat(),
        "main_net": _as_float(raw.get("main_net")),
        "change_pct": _as_float(raw.get("change_pct")),
    }
    return {k: row.get(k) for k in SECTOR_FUND_FLOW_COLUMNS}


def normalize_news_row(
    raw: dict[str, Any],
    *,
    source: str,
    default_symbol: str | None = None,
    default_sector_code: str | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Map a lightweight news feature row (no LLM summary required)."""
    sym_raw = raw.get("symbol") or default_symbol
    sector_raw = raw.get("sector_code") or default_sector_code
    symbol: str | None = None
    sector_code: str | None = None
    if sym_raw not in (None, ""):
        symbol = normalize_symbol(str(sym_raw), market=market)
    if sector_raw not in (None, ""):
        sector_code = normalize_sector_code(str(sector_raw))
    if symbol is None and sector_code is None:
        raise ValueError("news row missing symbol or sector_code")

    trade_date = _as_date(
        raw.get("date") or raw.get("trade_date") or raw.get("day") or raw.get("time")
    )
    if trade_date is None:
        raise ValueError("news row missing date")

    title = raw.get("title")
    if title in (None, ""):
        raise ValueError("news row missing title")

    summary = raw.get("summary") or raw.get("content")
    if summary is not None:
        summary = str(summary).strip() or None

    sentiment = raw.get("sentiment")
    sentiment_f = _as_float(sentiment) if sentiment not in (None, "") else None

    row = {
        "symbol": symbol,
        "sector_code": sector_code,
        "date": trade_date.isoformat(),
        "title": str(title).strip(),
        "summary": summary,
        "source": source,
        "sentiment": sentiment_f,
    }
    return {k: row.get(k) for k in NEWS_COLUMNS}


def normalize_concept_blocks_payload(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Map EM slist / fixture concept-block membership into contract fields."""
    sym_raw = raw.get("symbol") or default_symbol
    if sym_raw in (None, ""):
        raise ValueError("concept_blocks payload missing symbol")
    symbol = normalize_symbol(str(sym_raw), market=market)

    boards_in = raw.get("boards") or raw.get("items") or raw.get("diff") or []
    if isinstance(boards_in, dict):
        boards_in = list(boards_in.values())
    if not isinstance(boards_in, list):
        raise ValueError("concept_blocks boards must be a list")

    boards: list[dict[str, Any]] = []
    for item in boards_in:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("f14") or item.get("board_name")
        code_raw = item.get("code") or item.get("f12") or item.get("sector_code")
        if name in (None, "") and code_raw in (None, ""):
            continue
        code: str | None = None
        if code_raw not in (None, ""):
            try:
                code = normalize_sector_code(str(code_raw))
            except Exception:  # noqa: BLE001 — keep raw BK-like codes fail-soft
                code = str(code_raw).strip().upper() or None
        board = {
            "name": str(name).strip() if name not in (None, "") else "",
            "code": code or "",
            "change_pct": _as_float(item.get("change_pct") or item.get("f3")),
            "lead_stock": (
                str(item.get("lead_stock") or item.get("f128") or "").strip() or None
            ),
        }
        boards.append({k: board.get(k) for k in CONCEPT_BLOCK_COLUMNS})

    tags_raw = raw.get("concept_tags")
    if isinstance(tags_raw, list) and tags_raw:
        concept_tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        concept_tags = [b["name"] for b in boards if b.get("name")]

    total = raw.get("total")
    total_i = int(total) if total not in (None, "") else len(boards)

    out = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "total": total_i,
        "boards": boards,
        "concept_tags": concept_tags,
    }
    return {k: out.get(k) for k in CONCEPT_BLOCKS_TOP_KEYS}


def normalize_adj_factor_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Map an adjustment-factor event into contract fields (``ex_factor``).

    Accepts vendor aliases: ``d``/``date`` → ``trade_date``;
    ``f``/``factor``/``adj_factor`` → ``ex_factor``.
    """
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("adj_factor row missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    trade_date = _as_date(
        raw.get("trade_date") or raw.get("date") or raw.get("d") or raw.get("day")
    )
    if trade_date is None:
        raise ValueError(f"adj_factor row for {symbol} missing trade_date")

    factor_raw = None
    for key in ("ex_factor", "factor", "adj_factor", "f"):
        if raw.get(key) is not None and raw.get(key) != "":
            factor_raw = raw.get(key)
            break
    ex_factor = _as_float(factor_raw)
    if ex_factor is None:
        raise ValueError(f"adj_factor row for {symbol} missing ex_factor")

    row = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "trade_date": trade_date.isoformat(),
        "ex_factor": ex_factor,
    }
    return {k: row.get(k) for k in ADJ_FACTOR_COLUMNS}


def validate_adj_factor_kind(kind: str) -> str:
    """Return normalized kind or raise ValueError."""
    k = str(kind).strip().lower()
    if k not in ADJ_FACTOR_KINDS:
        raise ValueError(f"adj_factor kind must be qfq or hfq, got {kind!r}")
    return k


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


def _normalize_unlock_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one unlock event; shares/able_shares stay in 万股 (EM raw)."""
    d = _as_date(raw.get("date") or raw.get("FREE_DATE") or raw.get("free_date"))
    if d is None:
        return None
    event_type = str(
        raw.get("type")
        or raw.get("FREE_SHARES_TYPE")
        or raw.get("LIMITED_STOCK_TYPE")
        or ""
    )
    shares = _as_float(
        raw.get("shares")
        if "shares" in raw
        else raw.get("FREE_SHARES", raw.get("FREE_SHARES_NUM"))
    )
    able = _as_float(
        raw.get("able_shares")
        if "able_shares" in raw
        else raw.get("ABLE_FREE_SHARES")
    )
    ratio = _as_float(raw.get("ratio") if "ratio" in raw else raw.get("FREE_RATIO"))
    event = {
        "date": d.isoformat(),
        "type": event_type,
        "shares": shares,
        "able_shares": able,
        "ratio": ratio,
    }
    return {k: event.get(k) for k in UNLOCK_EVENT_COLUMNS}


def normalize_unlock_payload(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    asof_date: date | None = None,
    forward_days: int | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Normalize a lockup-expiry aggregate payload (shares in 万股).

    Empty ``history`` / ``upcoming`` lists are valid.
    """
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("unlock payload missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    asof = _as_date(raw.get("asof_date") or raw.get("trade_date") or asof_date)
    if asof is None:
        raise ValueError(f"unlock payload for {symbol} missing asof_date")

    forward = raw.get("forward_days", forward_days)
    if forward is None:
        forward = 90
    forward_i = int(forward)

    history: list[dict[str, Any]] = []
    for item in raw.get("history") or []:
        if not isinstance(item, dict):
            continue
        event = _normalize_unlock_event(item)
        if event is not None:
            history.append(event)

    upcoming: list[dict[str, Any]] = []
    for item in raw.get("upcoming") or []:
        if not isinstance(item, dict):
            continue
        event = _normalize_unlock_event(item)
        if event is not None:
            upcoming.append(event)

    payload = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "asof_date": asof.isoformat(),
        "forward_days": forward_i,
        "history": history,
        "upcoming": upcoming,
    }
    return {k: payload.get(k) for k in UNLOCK_TOP_KEYS}


def _as_level_list(value: Any, *, n: int = DEPTH5_LEVELS) -> list[float | None]:
    """Pad/truncate a price or volume ladder to exactly ``n`` floats (or None)."""
    if value is None:
        return [None] * n
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    out: list[float | None] = []
    for item in items[:n]:
        out.append(_as_float(item))
    while len(out) < n:
        out.append(None)
    return out


def normalize_depth5_row(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Map a five-level order book snapshot (prices 元, volumes 手)."""
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("depth5 row missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    bid_prices = _as_level_list(raw.get("bid_prices") or raw.get("bids"))
    bid_volumes = _as_level_list(raw.get("bid_volumes") or raw.get("bid_vols"))
    ask_prices = _as_level_list(raw.get("ask_prices") or raw.get("asks"))
    ask_volumes = _as_level_list(raw.get("ask_volumes") or raw.get("ask_vols"))

    # Accept parallel bid1..bid5 / ask1..ask5 style keys when arrays absent.
    if all(v is None for v in bid_prices) and any(f"bid{i}" in raw for i in range(1, 6)):
        bid_prices = [_as_float(raw.get(f"bid{i}")) for i in range(1, 6)]
    if all(v is None for v in bid_volumes) and any(
        f"bid_vol{i}" in raw or f"bid_volume{i}" in raw for i in range(1, 6)
    ):
        bid_volumes = [
            _as_float(raw.get(f"bid_vol{i}", raw.get(f"bid_volume{i}"))) for i in range(1, 6)
        ]
    if all(v is None for v in ask_prices) and any(f"ask{i}" in raw for i in range(1, 6)):
        ask_prices = [_as_float(raw.get(f"ask{i}")) for i in range(1, 6)]
    if all(v is None for v in ask_volumes) and any(
        f"ask_vol{i}" in raw or f"ask_volume{i}" in raw for i in range(1, 6)
    ):
        ask_volumes = [
            _as_float(raw.get(f"ask_vol{i}", raw.get(f"ask_volume{i}"))) for i in range(1, 6)
        ]

    asof = _as_ms(raw.get("asof_ts") or raw.get("timestamp") or raw.get("f86"))
    if asof is None:
        raise ValueError(f"depth5 row for {symbol} missing asof_ts")

    row = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "bid_prices": bid_prices,
        "bid_volumes": bid_volumes,
        "ask_prices": ask_prices,
        "ask_volumes": ask_volumes,
        "asof_ts": asof,
    }
    return {k: row.get(k) for k in DEPTH5_COLUMNS}


# Sina / vendor Chinese titles → canonical English keys (first match wins).
_INCOME_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "营业收入", "营业总收入", "operating_income"),
    "net_income": ("net_income", "净利润", "net_profit"),
    "net_income_attributable": (
        "net_income_attributable",
        "归属于母公司所有者的净利润",
        "归属于母公司股东的净利润",
        "归母净利润",
        "parent_holder_net_profit",
    ),
    "basic_eps": ("basic_eps", "基本每股收益", "basic_earnings_per_share"),
}

_BALANCE_ALIASES: dict[str, tuple[str, ...]] = {
    "total_assets": ("total_assets", "资产总计", "资产合计", "总资产", "assets_total"),
    "total_liabilities": (
        "total_liabilities",
        "负债合计",
        "负债总计",
        "总负债",
        "total_debt",
    ),
    "total_equity": (
        "total_equity",
        "所有者权益合计",
        "股东权益合计",
        "归属于母公司所有者权益合计",
        "holder_equity_total",
    ),
}

_CASHFLOW_ALIASES: dict[str, tuple[str, ...]] = {
    "net_operating_cash_flow": (
        "net_operating_cash_flow",
        "经营活动产生的现金流量净额",
        "act_cash_flow_net",
    ),
    "net_investing_cash_flow": (
        "net_investing_cash_flow",
        "投资活动产生的现金流量净额",
        "invest_cash_flow_net",
    ),
    "net_financing_cash_flow": (
        "net_financing_cash_flow",
        "筹资活动产生的现金流量净额",
        "finance_cash_flow_net",
    ),
}


def _pick_aliased(raw: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _normalize_statement_row(
    raw: dict[str, Any],
    *,
    columns: list[str],
    field_aliases: dict[str, tuple[str, ...]],
) -> dict[str, Any] | None:
    period = _as_date(
        raw.get("period_end")
        or raw.get("报告期")
        or raw.get("report_date")
        or raw.get("period")
    )
    if period is None:
        return None
    row: dict[str, Any] = {"period_end": period.isoformat()}
    for col in columns:
        if col == "period_end":
            continue
        aliases = field_aliases.get(col, (col,))
        row[col] = _as_float(_pick_aliased(raw, aliases))
    return {k: row.get(k) for k in columns}


def normalize_financial_payload(
    raw: dict[str, Any],
    *,
    source: str,
    asset_type: str = "stock",
    default_symbol: str | None = None,
    periods: int | None = None,
    market: str = "CN",
) -> dict[str, Any]:
    """Normalize a CN financial three-statement aggregate (amounts in 元).

    Empty statement lists are valid. ``periods`` defaults to max length of the
    three lists (or explicit override).
    """
    sym = raw.get("symbol") or raw.get("code") or default_symbol
    if not sym:
        raise ValueError("financial payload missing symbol")
    symbol = normalize_symbol(str(sym), market=market)

    income: list[dict[str, Any]] = []
    for item in raw.get("income") or raw.get("lrb") or []:
        if not isinstance(item, dict):
            continue
        row = _normalize_statement_row(
            item, columns=FINANCIAL_INCOME_COLUMNS, field_aliases=_INCOME_ALIASES
        )
        if row is not None:
            income.append(row)

    balance: list[dict[str, Any]] = []
    for item in raw.get("balance") or raw.get("fzb") or raw.get("balance_sheet") or []:
        if not isinstance(item, dict):
            continue
        row = _normalize_statement_row(
            item, columns=FINANCIAL_BALANCE_COLUMNS, field_aliases=_BALANCE_ALIASES
        )
        if row is not None:
            balance.append(row)

    cashflow: list[dict[str, Any]] = []
    for item in raw.get("cashflow") or raw.get("llb") or raw.get("cash_flow") or []:
        if not isinstance(item, dict):
            continue
        row = _normalize_statement_row(
            item, columns=FINANCIAL_CASHFLOW_COLUMNS, field_aliases=_CASHFLOW_ALIASES
        )
        if row is not None:
            cashflow.append(row)

    if periods is None:
        periods = raw.get("periods")
    if periods is None:
        periods_i = max(len(income), len(balance), len(cashflow), 0)
    else:
        periods_i = int(periods)

    payload = {
        "symbol": symbol,
        "asset_type": asset_type,
        "source": source,
        "periods": periods_i,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
    }
    return {k: payload.get(k) for k in FINANCIAL_TOP_KEYS}
