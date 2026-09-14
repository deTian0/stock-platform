"""US/HK live HTTP provider — Yahoo chart (daily) + Sina quotes (realtime).

Does **not** use ``em_get`` / East Money throttle (CN-only path).
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Literal
from urllib.parse import quote

from .base import AssetType
from .errors import SymbolError
from .normalize import normalize_daily_row, normalize_realtime_row
from .symbol import normalize_symbol

MarketId = Literal["US", "HK"]

YAHOO_CHART = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
SINA_HQ = "https://hq.sinajs.cn/list={list_id}"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
SINA_REFERER = "https://finance.sina.com.cn/"

_SINA_QUOTE_RE = re.compile(r'"(.+)"')


def yahoo_symbol(symbol: str, *, market: MarketId) -> str:
    """Map normalized platform symbol to Yahoo chart ticker."""
    if market == "US":
        return symbol
    # HK: platform uses 5-digit (00700) → Yahoo 00700.HK
    return f"{symbol}.HK"


def sina_list_id(symbol: str, *, market: MarketId) -> str:
    if market == "US":
        return f"gb_{symbol.lower()}"
    return f"rt_hk{symbol}"


def infer_global_market(raw: str) -> MarketId:
    """Infer US vs HK from a ticker; reject CN 6-digit forms."""
    original = raw.strip()
    if not original:
        raise SymbolError("ticker must be a non-empty string")
    s = original.upper().replace(" ", "")
    if s.endswith(".HK") or (s.startswith("HK") and len(s) > 2 and s[2:].replace(".", "").isdigit()):
        return "HK"
    body = s
    for suffix in (".US", ".NYSE", ".NASDAQ"):
        if body.endswith(suffix):
            body = body[: -len(suffix)]
            break
    if body.isdigit():
        if len(body) == 6:
            raise SymbolError(
                f"{original!r} looks like an A-share code; "
                "global_http only accepts US/HK. Use astock_http / replay for CN."
            )
        if 1 <= len(body) <= 5:
            return "HK"
        raise SymbolError(f"{original!r} is not a valid US/HK ticker")
    return "US"


def _parse_sina_us_fields(fields: list[str]) -> dict[str, Any]:
    if len(fields) < 30:
        raise ValueError(f"short sina US quote ({len(fields)} fields)")
    return {
        "name": fields[0],
        "price": fields[1],
        "change_pct": fields[2],
        "open": fields[5],
        "high": fields[6],
        "low": fields[7],
        "volume": fields[10] or 0,
        "prev_close": fields[26],
        "pct_unit": "percent",
        "asof_ts": int(time.time() * 1000),
    }


def _parse_sina_hk_fields(fields: list[str]) -> dict[str, Any]:
    if len(fields) < 15:
        raise ValueError(f"short sina HK quote ({len(fields)} fields)")
    return {
        "name": fields[1],
        "open": fields[2],
        "prev_close": fields[3],
        "high": fields[4],
        "low": fields[5],
        "price": fields[6],
        "change": fields[7],
        "change_pct": fields[8],
        "amount": fields[11] if len(fields) > 11 else None,
        "volume": fields[12] if len(fields) > 12 else 0,
        "pct_unit": "percent",
        "asof_ts": int(time.time() * 1000),
    }


def parse_sina_quote_text(text: str, *, market: MarketId) -> dict[str, Any]:
    m = _SINA_QUOTE_RE.search(text)
    if not m:
        raise ValueError("sina quote payload missing quoted fields")
    fields = m.group(1).split(",")
    if market == "US":
        return _parse_sina_us_fields(fields)
    return _parse_sina_hk_fields(fields)


def parse_yahoo_chart(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chart = (payload.get("chart") or {}).get("result") or []
    if not chart:
        return []
    result = chart[0] or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0] or {}
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        rows.append(
            {
                "date": day,
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": close,
                "volume": volumes[i] if i < len(volumes) else None,
            }
        )
    return rows


def _default_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    import requests

    resp = requests.get(
        url,
        params=params or {},
        headers={"User-Agent": DEFAULT_UA},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _default_get_text(url: str, *, encoding: str = "gbk") -> str:
    import requests

    resp = requests.get(
        url,
        headers={"User-Agent": DEFAULT_UA, "Referer": SINA_REFERER},
        timeout=10,
    )
    resp.raise_for_status()
    resp.encoding = encoding
    return resp.text


class GlobalHttpProvider:
    """MarketDataProvider for one US or HK market via Yahoo + Sina."""

    name = "global_http"

    def __init__(
        self,
        *,
        market: MarketId,
        get_json: Callable[..., dict[str, Any]] | None = None,
        get_text: Callable[..., str] | None = None,
    ) -> None:
        if market not in ("US", "HK"):
            raise SymbolError(f"GlobalHttpProvider market must be US or HK, got {market!r}")
        self.market = market
        self._get_json = get_json
        self._get_text = get_text

    def _fetch_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._get_json is not None:
            return self._get_json(url, params=params)
        return _default_get_json(url, params=params)

    def _fetch_text(self, url: str) -> str:
        if self._get_text is not None:
            return self._get_text(url)
        return _default_get_text(url)

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym, market=self.market)
            ysym = yahoo_symbol(symbol, market=self.market)
            url = YAHOO_CHART.format(symbol=quote(ysym, safe="."))
            params: dict[str, Any] = {"interval": "1d"}
            if start is not None or end is not None:
                # Yahoo period bounds are unix seconds (UTC day edges).
                beg = start or date(1990, 1, 1)
                fin = end or date.today()
                params["period1"] = int(
                    datetime(beg.year, beg.month, beg.day, tzinfo=timezone.utc).timestamp()
                )
                # exclusive-ish end: include end day by +1 day
                end_exclusive = datetime(
                    fin.year, fin.month, fin.day, tzinfo=timezone.utc
                ).timestamp() + 86400
                params["period2"] = int(end_exclusive)
            else:
                params["range"] = "max"
            payload = self._fetch_json(url, params=params)
            for bar in parse_yahoo_chart(payload):
                bar["symbol"] = symbol
                row = normalize_daily_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    market=self.market,
                )
                d = date.fromisoformat(row["date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                rows.append(row)
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            symbol = normalize_symbol(raw_sym, market=self.market)
            list_id = sina_list_id(symbol, market=self.market)
            url = SINA_HQ.format(list_id=list_id)
            text = self._fetch_text(url)
            raw = parse_sina_quote_text(text, market=self.market)
            raw["symbol"] = symbol
            rows.append(
                normalize_realtime_row(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=symbol,
                    market=self.market,
                )
            )
        return rows


class GlobalHttpRouter:
    """Single matrix name ``global_http``; routes each symbol to US or HK provider."""

    name = "global_http"

    def __init__(
        self,
        *,
        us: GlobalHttpProvider | None = None,
        hk: GlobalHttpProvider | None = None,
        get_json: Callable[..., dict[str, Any]] | None = None,
        get_text: Callable[..., str] | None = None,
    ) -> None:
        self._us = us or GlobalHttpProvider(market="US", get_json=get_json, get_text=get_text)
        self._hk = hk or GlobalHttpProvider(market="HK", get_json=get_json, get_text=get_text)

    def _provider_for(self, raw_sym: str) -> GlobalHttpProvider:
        market = infer_global_market(raw_sym)
        return self._us if market == "US" else self._hk

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            rows.extend(
                self._provider_for(raw_sym).get_daily(
                    [raw_sym], start=start, end=end, asset_type=asset_type
                )
            )
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            rows.extend(
                self._provider_for(raw_sym).get_realtime([raw_sym], asset_type=asset_type)
            )
        return rows
