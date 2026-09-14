"""A-share live HTTP provider — East Money via em_get; financial/adj_factor via Sina."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .base import AssetType
from .eastmoney import EastmoneyClient, get_default_client
from .normalize import (
    normalize_adj_factor_row,
    normalize_daily_row,
    normalize_depth5_row,
    normalize_financial_payload,
    normalize_fund_flow_row,
    normalize_lhb_payload,
    normalize_minute_row,
    normalize_realtime_row,
    normalize_unlock_payload,
    validate_adj_factor_kind,
)
from .schemas import FULL_MINUTE_DEFAULT_COUNT, FULL_MINUTE_FREQ
from .symbol import exchange_prefix, normalize_symbol

_CN_TZ = ZoneInfo("Asia/Shanghai")

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
FUND_FLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SINA_FINANCE_URL = (
    "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
)
SINA_ADJ_FACTOR_TMPL = "https://finance.sina.com.cn/realstock/company/{paper}/{kind}.js"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
SINA_REFERER = "https://finance.sina.com.cn/"

# Sina report_type → contract statement key
_SINA_REPORT_TYPES: tuple[tuple[str, str], ...] = (
    ("lrb", "income"),
    ("fzb", "balance"),
    ("llb", "cashflow"),
)

# East Money klt → contract freq (minute only; 101=daily used separately).
_MINUTE_KLT: dict[str, str] = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}

# push2 stock/get five-level book (fltt=2): (price_field, volume_field) bid1→5 / ask1→5.
_DEPTH5_BID_FIELDS: tuple[tuple[str, str], ...] = (
    ("f19", "f20"),
    ("f17", "f18"),
    ("f15", "f16"),
    ("f13", "f14"),
    ("f11", "f12"),
)
_DEPTH5_ASK_FIELDS: tuple[tuple[str, str], ...] = (
    ("f39", "f40"),
    ("f37", "f38"),
    ("f35", "f36"),
    ("f33", "f34"),
    ("f31", "f32"),
)
_DEPTH5_FIELDS = (
    "f86,"
    + ",".join(f"{p},{v}" for p, v in _DEPTH5_BID_FIELDS + _DEPTH5_ASK_FIELDS)
)


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


def _parse_minute_kline_csv(line: str) -> dict[str, Any]:
    """EM minute kline CSV: datetime,open,close,high,low,volume,amount,..."""
    parts = line.split(",")
    if len(parts) < 7:
        raise ValueError(f"short minute kline row: {line!r}")
    return {
        "datetime": parts[0],
        "open": parts[1],
        "close": parts[2],
        "high": parts[3],
        "low": parts[4],
        "volume": parts[5],
        "amount": parts[6] if parts[6] not in {"", "-"} else None,
    }


class AStockHttpProvider:
    """MarketDataProvider: East Money via ``em_get``; Sina for financial/adj_factor."""

    name = "astock_http"

    def __init__(
        self,
        client: EastmoneyClient | None = None,
        *,
        get_json: Callable[..., dict[str, Any]] | None = None,
        get_text: Callable[..., str] | None = None,
    ) -> None:
        self._client = client or get_default_client()
        self._get_json = get_json
        self._get_text = get_text

    def _fetch(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._get_json is not None:
            return self._get_json(url, params=params)
        resp = self._client.get(url, params=params)
        return _response_json(resp)

    def _fetch_sina(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Non-EM HTTP (Sina JSON). Must not go through ``em_get``."""
        if self._get_json is not None:
            return self._get_json(url, params=params)
        import requests

        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": DEFAULT_UA, "Referer": SINA_REFERER},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _fetch_sina_text(self, url: str) -> str:
        """Non-EM HTTP text (Sina JS payloads). Must not go through ``em_get``."""
        if self._get_text is not None:
            return self._get_text(url)
        import requests

        resp = requests.get(
            url,
            headers={"User-Agent": DEFAULT_UA, "Referer": SINA_REFERER},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.text

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

    def get_minute(
        self,
        symbols: list[str],
        *,
        freq: str = "1m",
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        """Intraday bars via push2his kline/get (klt=1/5/15/30/60).

        ``datetime`` is East Money Beijing wall clock (naive); never store as UTC.
        """
        want = str(freq).strip().lower()
        if want.isdigit():
            want = f"{want}m"
        klt = _MINUTE_KLT.get(want)
        if klt is None:
            raise ValueError(f"unsupported minute freq: {freq!r}")

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
                    "klt": klt,
                    "fqt": "0",
                    "beg": beg,
                    "end": end_s,
                    "lmt": "1000000",
                },
            )
            data = payload.get("data") or {}
            klines = data.get("klines") or []
            sym_rows: list[dict[str, Any]] = []
            for line in klines:
                raw = _parse_minute_kline_csv(str(line))
                raw["symbol"] = code
                raw["freq"] = want
                row = normalize_minute_row(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    default_freq=want,
                    market="CN",
                )
                bar_day = date.fromisoformat(row["datetime"][:10])
                if start and bar_day < start:
                    continue
                if end and bar_day > end:
                    continue
                sym_rows.append(row)
            if limit > 0:
                sym_rows = sym_rows[-limit:]
            rows.extend(sym_rows)
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

    def get_unlock(
        self,
        symbols: list[str],
        *,
        asof_date: date,
        forward_days: int = 90,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Lockup expiry calendar via datacenter-web (shares in 万股).

        Empty history / upcoming windows return empty lists (no crash).
        Column names follow a-stock-data §3.6 (FREE_SHARES_TYPE / FREE_SHARES).
        """
        items: list[dict[str, Any]] = []
        forward = max(1, int(forward_days))
        end_date = asof_date + timedelta(days=forward)
        asof_s = asof_date.isoformat()
        end_s = end_date.isoformat()

        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            history_raw = self._datacenter(
                "RPT_LIFT_STAGE",
                filter_str=f'(SECURITY_CODE="{code}")',
                page_size=15,
                sort_columns="FREE_DATE",
                sort_types="-1",
            )
            upcoming_raw = self._datacenter(
                "RPT_LIFT_STAGE",
                filter_str=(
                    f'(SECURITY_CODE="{code}")'
                    f"(FREE_DATE>='{asof_s}')"
                    f"(FREE_DATE<='{end_s}')"
                ),
                page_size=20,
                sort_columns="FREE_DATE",
                sort_types="1",
            )

            def _row_event(row: dict[str, Any]) -> dict[str, Any]:
                return {
                    "date": str(row.get("FREE_DATE", ""))[:10],
                    "type": row.get("FREE_SHARES_TYPE")
                    or row.get("LIMITED_STOCK_TYPE")
                    or "",
                    "shares": row.get("FREE_SHARES", row.get("FREE_SHARES_NUM")),
                    "able_shares": row.get("ABLE_FREE_SHARES"),
                    "ratio": row.get("FREE_RATIO"),
                }

            raw_payload = {
                "symbol": code,
                "asof_date": asof_s,
                "forward_days": forward,
                "history": [_row_event(r) for r in history_raw],
                "upcoming": [_row_event(r) for r in upcoming_raw],
            }
            items.append(
                normalize_unlock_payload(
                    raw_payload,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    asof_date=asof_date,
                    forward_days=forward,
                    market="CN",
                )
            )
        return items

    def get_depth5(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Five-level order book via push2 stock/get (volumes in 手).

        Same URL as realtime; empty ``data`` skips the symbol (no crash).
        """
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            payload = self._fetch(
                QUOTE_URL,
                {
                    "fltt": "2",
                    "invt": "2",
                    "secid": em_secid(code),
                    "fields": _DEPTH5_FIELDS,
                },
            )
            d = payload.get("data") or {}
            if not d:
                continue
            bid_prices: list[Any] = []
            bid_volumes: list[Any] = []
            ask_prices: list[Any] = []
            ask_volumes: list[Any] = []
            for price_f, vol_f in _DEPTH5_BID_FIELDS:
                bid_prices.append(d.get(price_f))
                bid_volumes.append(d.get(vol_f))
            for price_f, vol_f in _DEPTH5_ASK_FIELDS:
                ask_prices.append(d.get(price_f))
                ask_volumes.append(d.get(vol_f))
            raw = {
                "symbol": code,
                "bid_prices": bid_prices,
                "bid_volumes": bid_volumes,
                "ask_prices": ask_prices,
                "ask_volumes": ask_volumes,
                "asof_ts": d.get("f86") or int(__import__("time").time() * 1000),
            }
            rows.append(
                normalize_depth5_row(
                    raw,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    market="CN",
                )
            )
        return rows

    def get_financial(
        self,
        symbols: list[str],
        *,
        periods: int = 8,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """CN three-statement financials via Sina (not East Money / em_get).

        Empty report_list for all three statements skips the symbol.
        """
        num = max(1, int(periods))
        items: list[dict[str, Any]] = []
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            paper = f"{exchange_prefix(code)}{code}"
            statements: dict[str, list[dict[str, Any]]] = {
                "income": [],
                "balance": [],
                "cashflow": [],
            }
            for report_type, key in _SINA_REPORT_TYPES:
                payload = self._fetch_sina(
                    SINA_FINANCE_URL,
                    {
                        "paperCode": paper,
                        "source": report_type,
                        "type": "0",
                        "page": "1",
                        "num": str(num),
                    },
                )
                statements[key] = _parse_sina_finance_report(payload, num=num)
            if not (statements["income"] or statements["balance"] or statements["cashflow"]):
                continue
            raw_payload = {
                "symbol": code,
                "periods": num,
                **statements,
            }
            items.append(
                normalize_financial_payload(
                    raw_payload,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    periods=num,
                    market="CN",
                )
            )
        return items

    def get_adj_factor(
        self,
        symbols: list[str],
        *,
        kind: str = "qfq",
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        """CN adjustment factors via Sina JS (not East Money / em_get).

        Default ``kind=qfq`` (forward). Empty ``data`` skips the symbol.
        """
        kind_n = validate_adj_factor_kind(kind)
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            paper = f"{exchange_prefix(code)}{code}"
            url = SINA_ADJ_FACTOR_TMPL.format(paper=paper, kind=kind_n)
            text = self._fetch_sina_text(url)
            factors = _parse_sina_adj_factor_js(text)
            if not factors:
                continue
            sym_rows: list[dict[str, Any]] = []
            for item in factors:
                row = normalize_adj_factor_row(
                    item,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    market="CN",
                )
                d = date.fromisoformat(row["trade_date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                sym_rows.append(row)
            # Sina returns newest-first; keep that after filters
            sym_rows.sort(key=lambda r: r["trade_date"], reverse=True)
            if limit > 0:
                sym_rows = sym_rows[:limit]
            rows.extend(sym_rows)
        return rows

    def get_full_minute(
        self,
        symbols: list[str],
        *,
        trade_date: date | None = None,
        count: int = FULL_MINUTE_DEFAULT_COUNT,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Same-day 1m batch via push2his kline (klt=1) — distinct from multi-freq ``get_minute``.

        ``trade_date=None`` → Asia/Shanghai today. Empty klines skip the symbol.
        """
        if count < 0:
            raise ValueError(f"full_minute count must be >= 0, got {count}")
        day = trade_date or datetime.now(_CN_TZ).date()
        # Reuse get_minute path (em_get) with fixed 1m + single-day window.
        return self.get_minute(
            symbols,
            freq=FULL_MINUTE_FREQ,
            start=day,
            end=day,
            asset_type=asset_type,
            limit=count if count > 0 else 0,
        )


def _parse_sina_adj_factor_js(text: str) -> list[dict[str, Any]]:
    """Parse Sina ``var xxqfq={...}/* base64 */`` into date/factor rows.

    Must use ``JSONDecoder.raw_decode`` from the first ``{`` — trailing comment
    blocks break ``$``-anchored regexes (a-stock-data §1.4).
    """
    brace = text.find("{")
    if brace < 0:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(text[brace:])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []
    for it in data.get("data") or []:
        if not isinstance(it, dict):
            continue
        out.append({"date": it.get("d"), "factor": it.get("f")})
    return out


def _parse_sina_finance_report(payload: dict[str, Any], *, num: int) -> list[dict[str, Any]]:
    """Parse Sina ``report_list`` into period_end + Chinese title rows."""
    report_list = ((payload.get("result") or {}).get("data") or {}).get("report_list") or {}
    if not isinstance(report_list, dict):
        return []
    rows: list[dict[str, Any]] = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period] or {}
        period_s = str(period)
        if len(period_s) == 8 and period_s.isdigit():
            period_end = f"{period_s[:4]}-{period_s[4:6]}-{period_s[6:8]}"
        else:
            period_end = period_s
        rec: dict[str, Any] = {"period_end": period_end, "报告期": period_end}
        for it in obj.get("data", []) or []:
            if not isinstance(it, dict):
                continue
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None:
                continue
            rec[title] = it.get("item_value")
        rows.append(rec)
    return rows


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