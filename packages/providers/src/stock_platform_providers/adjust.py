"""Deterministic OHLC adjustment using adj_factor rows (no HTTP)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Sequence

from .normalize import validate_adj_factor_kind

DEFAULT_PRICE_KEYS = ("open", "high", "low", "close", "pre_close")


def _as_date_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def _bar_date(bar: dict[str, Any]) -> str:
    raw = bar.get("date") or bar.get("trade_date") or bar.get("datetime")
    day = _as_date_str(raw)
    if day is None:
        raise ValueError(f"each bar needs date/trade_date, keys={sorted(bar)}")
    return day


def _factor_date(row: dict[str, Any]) -> str:
    raw = row.get("trade_date") or row.get("date") or row.get("d") or row.get("day")
    day = _as_date_str(raw)
    if day is None:
        raise ValueError(f"each factor row needs trade_date/date, keys={sorted(row)}")
    return day


def _factor_value(row: dict[str, Any]) -> float:
    for key in ("ex_factor", "factor", "adj_factor", "f"):
        val = row.get(key)
        if val is not None and val != "":
            return float(val)
    raise ValueError(f"factor row missing ex_factor, keys={sorted(row)}")


def _apply_one_symbol(
    bars: Sequence[dict[str, Any]],
    factors: Sequence[dict[str, Any]],
    *,
    kind: str,
    price_keys: Sequence[str],
) -> list[dict[str, Any]]:
    if not factors:
        raise ValueError(
            "adj_factor list is empty; refusing unadjusted prices "
            "(do not treat raw OHLC as adjusted)"
        )
    fac = sorted(factors, key=_factor_date)
    out: list[dict[str, Any]] = []
    i = 0
    cur: float | None = None
    first_day = _factor_date(fac[0])
    for bar in sorted(bars, key=_bar_date):
        day = _bar_date(bar)
        while i < len(fac) and _factor_date(fac[i]) <= day:
            cur = _factor_value(fac[i])
            i += 1
        if cur is None:
            raise ValueError(
                f"bar date {day} is earlier than first factor date {first_day}; "
                "refusing mixed adjusted/unadjusted rows"
            )
        if cur == 0:
            raise ValueError(f"adj_factor is 0 on {day}; cannot scale prices")
        nb = dict(bar)
        for key in price_keys:
            if key in nb and nb[key] is not None and nb[key] != "":
                raw = float(nb[key])
                nb[key] = round(raw / cur if kind == "qfq" else raw * cur, 4)
        nb["ex_factor"] = cur
        nb["adjust_kind"] = kind
        out.append(nb)
    return out


def apply_adjust(
    bars: Iterable[dict[str, Any]],
    factors: Sequence[dict[str, Any]],
    *,
    kind: str = "qfq",
    price_keys: Sequence[str] = DEFAULT_PRICE_KEYS,
) -> list[dict[str, Any]]:
    """Scale unadjusted OHLC with Sina-style qfq/hfq factors.

    - ``qfq``: adjusted = raw / ex_factor (divisor)
    - ``hfq``: adjusted = raw * ex_factor (multiplier)

    Factor table is a step function: each bar uses the latest factor whose
    date is not after the bar date. Empty factors or uncovered early bars fail
    closed (never return raw prices as if they were adjusted).
    """
    kind_n = validate_adj_factor_kind(kind)
    rows = [dict(b) for b in bars]
    if not rows:
        return []
    if not factors:
        raise ValueError(
            "adj_factor list is empty; refusing unadjusted prices "
            "(do not treat raw OHLC as adjusted)"
        )

    bars_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: list[str] = []
    for bar in rows:
        sym = str(bar.get("symbol") or "")
        if sym not in bars_by:
            order.append(sym)
        bars_by[sym].append(bar)

    fac_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in factors:
        fac_by[str(row.get("symbol") or "")].append(dict(row))
    factors_have_symbol = any(k for k in fac_by if k)
    bar_symbols = {s for s in bars_by if s}
    if len(bar_symbols) > 1 and not factors_have_symbol:
        raise ValueError("mixed-symbol bars require factor rows with symbol")

    out: list[dict[str, Any]] = []
    for sym in order:
        if factors_have_symbol:
            fac = fac_by.get(sym) or []
            if not fac:
                raise ValueError(f"no adj_factor rows for symbol {sym or '<missing>'}")
        else:
            fac = list(factors)
        out.extend(
            _apply_one_symbol(bars_by[sym], fac, kind=kind_n, price_keys=price_keys)
        )
    return out
