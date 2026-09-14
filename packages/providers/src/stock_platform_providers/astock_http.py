"""A-share live HTTP provider — East Money push2/push2his via em_get only."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from .base import AssetType
from .eastmoney import EastmoneyClient, get_default_client
from .normalize import (
    normalize_daily_row,
    normalize_fund_flow_row,
    normalize_lhb_payload,
    normalize_realtime_row,
)
from .symbol import exchange_prefix, normalize_symbol

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
FUND_FLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


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

    def get_fund_flow(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        """Day-level fund flow via push2his fflow/daykline (amounts in 元)."""
        rows: list[dict[str, Any]] = []
        lmt = max(1, min(int(limit), 1000))
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            payload = self._fetch(
                FUND_FLOW_URL,
                {
                    "secid": em_secid(code),
                    "fields1": "f1,f2,f3,f7",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                    "lmt": str(lmt),
                },
            )
            data = payload.get("data") or {}
            klines = data.get("klines") or []
            for line in klines:
                raw = _parse_fund_flow_csv(str(line))
                raw["symbol"] = code
                row = normalize_fund_flow_row(
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

    def _datacenter(
        self,
        report_name: str,
        *,
        filter_str: str = "",
        page_size: int = 50,
        sort_columns: str = "",
        sort_types: str = "-1",
    ) -> list[dict[str, Any]]:
        """East Money datacenter-web query via em_get / injected get_json."""
        payload = self._fetch(
            DATACENTER_URL,
            {
                "reportName": report_name,
                "columns": "ALL",
                "filter": filter_str,
                "pageNumber": "1",
                "pageSize": str(page_size),
                "sortColumns": sort_columns,
                "sortTypes": sort_types,
                "source": "WEB",
                "client": "WEB",
            },
        )
        result = payload.get("result") or {}
        data = result.get("data") or []
        return list(data) if isinstance(data, list) else []

    def get_lhb(
        self,
        symbols: list[str],
        *,
        asof_date: date,
        look_back_days: int = 30,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Dragon-tiger board via datacenter-web (amounts in 元).

        Empty look-back windows return empty records/seats and zero institution
        (no crash) — aligned with a-stock-data #45.
        """
        items: list[dict[str, Any]] = []
        look_back = max(1, int(look_back_days))
        start = asof_date - timedelta(days=look_back)
        start_s = start.isoformat()
        end_s = asof_date.isoformat()

        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            records_raw = self._datacenter(
                "RPT_DAILYBILLBOARD_DETAILSNEW",
                filter_str=(
                    f"(TRADE_DATE>='{start_s}')"
                    f"(TRADE_DATE<='{end_s}')"
                    f"(SECURITY_CODE=\"{code}\")"
                ),
                page_size=50,
                sort_columns="TRADE_DATE",
                sort_types="-1",
            )

            buy_data: list[dict[str, Any]] = []
            sell_data: list[dict[str, Any]] = []
            seats: dict[str, list[dict[str, Any]]] = {"buy": [], "sell": []}
            if records_raw:
                latest = str(records_raw[0].get("TRADE_DATE", ""))[:10]
                buy_data = self._datacenter(
                    "RPT_BILLBOARD_DAILYDETAILSBUY",
                    filter_str=f"(TRADE_DATE='{latest}')(SECURITY_CODE=\"{code}\")",
                    page_size=10,
                    sort_columns="BUY",
                    sort_types="-1",
                )
                for row in buy_data[:5]:
                    seats["buy"].append(
                        {
                            "name": row.get("OPERATEDEPT_NAME", ""),
                            "buy_amt": row.get("BUY"),
                            "sell_amt": row.get("SELL"),
                            "net": row.get("NET"),
                        }
                    )
                sell_data = self._datacenter(
                    "RPT_BILLBOARD_DAILYDETAILSSELL",
                    filter_str=f"(TRADE_DATE='{latest}')(SECURITY_CODE=\"{code}\")",
                    page_size=10,
                    sort_columns="SELL",
                    sort_types="-1",
                )
                for row in sell_data[:5]:
                    seats["sell"].append(
                        {
                            "name": row.get("OPERATEDEPT_NAME", ""),
                            "buy_amt": row.get("BUY"),
                            "sell_amt": row.get("SELL"),
                            "net": row.get("NET"),
                        }
                    )

            inst_buy = 0.0
            inst_sell = 0.0
            for detail, side in ((buy_data, "buy"), (sell_data, "sell")):
                for row in detail:
                    if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                        if side == "buy":
                            inst_buy += float(row.get("BUY") or 0)
                        else:
                            inst_sell += float(row.get("SELL") or 0)

            raw_payload = {
                "symbol": code,
                "asof_date": asof_date.isoformat(),
                "look_back_days": look_back,
                "records": [
                    {
                        "date": str(r.get("TRADE_DATE", ""))[:10],
                        "reason": r.get("EXPLANATION", ""),
                        "net_buy": r.get("BILLBOARD_NET_AMT"),
                        "turnover_rate": r.get("TURNOVERRATE"),
                        "pct_unit": "percent",
                    }
                    for r in records_raw
                ],
                "seats": seats,
                "institution": {
                    "buy_amt": inst_buy,
                    "sell_amt": inst_sell,
                    "net_amt": inst_buy - inst_sell,
                },
            }
            items.append(
                normalize_lhb_payload(
                    raw_payload,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    asof_date=asof_date,
                    look_back_days=look_back,
                    market="CN",
                )
            )
        return items


def _parse_fund_flow_csv(line: str) -> dict[str, Any]:
    """EM fflow daykline CSV: date,main,small,mid,large,super,..."""
    parts = line.split(",")
    if len(parts) < 6:
        raise ValueError(f"short fund_flow row: {line!r}")

    def _net(idx: int) -> float | None:
        if idx >= len(parts) or parts[idx] in {"", "-"}:
            return None
        return float(parts[idx])

    return {
        "date": parts[0],
        "main_net": _net(1),
        "small_net": _net(2),
        "mid_net": _net(3),
        "large_net": _net(4),
        "super_net": _net(5),
    }