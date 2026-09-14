"""A-share live HTTP provider — East Money push2/push2his via em_get only."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from .base import AssetType
from .eastmoney import EastmoneyClient, get_default_client
from .normalize import normalize_daily_row, normalize_realtime_row
from .symbol import exchange_prefix, normalize_symbol

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"


def em_secid(code: str) -> str:
    """East Money secid: Shanghai=1.*, Shenzhen/BSE=0.*"""
    prefix = exchange_prefix(code)
    market = 1 if prefix == "sh" else 0
    return f"{market}.{code}"


def _response_json(resp: Any) -> dict[str, Any]:
    if isinstance(resp, dict):
        return resp
    if hasattr(resp, "json"):
        return resp.json()
    raise TypeError(f"unexpected em_get response type: {type(resp)!r}")


def _parse_kline_csv(line: str) -> dict[str, Any]:
    """EM daily kline CSV: date,open,close,high,low,volume,amount,...,change_pct,..."""
    parts = line.split(",")
    if len(parts) < 7:
        raise ValueError(f"short kline row: {line!r}")
    # f59 is change_pct in percent when present (index 8)
    change_pct = None
    if len(parts) > 8 and parts[8] not in {"", "-"}:
        change_pct = parts[8]
    return {
        "date": parts[0],
        "open": parts[1],
        "close": parts[2],
        "high": parts[3],
        "low": parts[4],
        "volume": parts[5],
        "amount": parts[6],
        "change_pct": change_pct,
        "pct_unit": "percent" if change_pct is not None else None,
    }


class AStockHttpProvider:
    """MarketDataProvider backed by East Money HTTP through ``EastmoneyClient``."""

    name = "astock_http"

    def __init__(
        self,
        client: EastmoneyClient | None = None,
        *,
        get_json: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._client = client or get_default_client()
        self._get_json = get_json

    def _fetch(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._get_json is not None:
            return self._get_json(url, params=params)
        resp = self._client.get(url, params=params)
        return _response_json(resp)

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        beg = (start or date(1990, 1, 1)).strftime("%Y%m%d")
        end_s = (end or date(2099, 12, 31)).strftime("%Y%m%d")
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            payload = self._fetch(
                KLINE_URL,
                {
                    "secid": em_secid(code),
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                    "klt": "101",
                    "fqt": "0",
                    "beg": beg,
                    "end": end_s,
                    "lmt": "1000000",
                },
            )
            data = payload.get("data") or {}
            klines = data.get("klines") or []
            for line in klines:
                raw = _parse_kline_csv(str(line))
                raw["symbol"] = code
                row = normalize_daily_row(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    market="CN",
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
            code = normalize_symbol(raw_sym, market="CN")
            payload = self._fetch(
                QUOTE_URL,
                {
                    "fltt": "2",
                    "invt": "2",
                    "secid": em_secid(code),
                    "fields": "f43,f57,f58,f60,f169,f170,f171,f168,f47,f48,f46,f44,f45",
                },
            )
            d = payload.get("data") or {}
            if not d:
                continue
            raw = {
                "symbol": code,
                "name": d.get("f58"),
                "price": d.get("f43"),
                "prev_close": d.get("f60"),
                "change": d.get("f169"),
                "pct": d.get("f170"),
                "amplitude": d.get("f171"),
                "turnover_rate": d.get("f168"),
                "volume": d.get("f47"),
                "amount": d.get("f48"),
                "pct_unit": "percent",
                "asof_ts": d.get("f86") or int(__import__("time").time() * 1000),
            }
            rows.append(
                normalize_realtime_row(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    market="CN",
                )
            )
        return rows
