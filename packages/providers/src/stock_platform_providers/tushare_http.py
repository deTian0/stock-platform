"""Tushare-compatible HTTP provider — raw POST ``api_name`` (no tushare SDK dep).

Compatible with official Tushare Pro and compatible mirrors. Token/URL come from
env only — never hard-code secrets.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Callable

from .base import AssetType
from .normalize import normalize_daily_row
from .symbol import exchange_prefix, normalize_symbol

ENV_TUSHARE_TOKEN = "STOCK_PLATFORM_TUSHARE_TOKEN"
ENV_TUSHARE_URL = "STOCK_PLATFORM_TUSHARE_URL"
DEFAULT_TUSHARE_URL = "https://t.xiaodefa.top/"

# Tushare ``daily`` fields we request (pro_bar-equivalent unadjusted bars).
_DAILY_FIELDS = (
    "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
)

PostJson = Callable[..., dict[str, Any]]


class TushareHttpError(RuntimeError):
    """Upstream Tushare-compatible API returned a non-zero code or bad payload."""


def to_ts_code(symbol: str) -> str:
    """Map platform CN 6-digit code to Tushare ``ts_code`` (e.g. ``600519.SH``)."""
    code = normalize_symbol(symbol, market="CN")
    prefix = exchange_prefix(code)
    suffix = {"sh": "SH", "sz": "SZ", "bj": "BJ"}[prefix]
    return f"{code}.{suffix}"


def from_ts_code(ts_code: str) -> str:
    """Map Tushare ``ts_code`` back to platform 6-digit CN symbol."""
    return normalize_symbol(str(ts_code).strip(), market="CN")


def resolve_tushare_url(url: str | None = None, *, env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    raw = (url if url is not None else source.get(ENV_TUSHARE_URL, "") or "").strip()
    if not raw:
        raw = DEFAULT_TUSHARE_URL
    return raw if raw.endswith("/") else raw + "/"


def resolve_tushare_token(
    token: str | None = None, *, env: dict[str, str] | None = None
) -> str:
    source = env if env is not None else os.environ
    raw = (token if token is not None else source.get(ENV_TUSHARE_TOKEN, "") or "").strip()
    return raw


def rows_from_tushare_data(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Convert Tushare ``data.fields`` + ``data.items`` into list[dict]."""
    if not data:
        return []
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not fields:
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, (list, tuple)):
            continue
        row = {fields[i]: item[i] for i in range(min(len(fields), len(item)))}
        out.append(row)
    return out


def _default_post_json(url: str, body: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:
    import requests

    from .eastmoney import http_trust_env

    with requests.Session() as session:
        session.trust_env = http_trust_env()
        resp = session.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise TushareHttpError(f"unexpected Tushare response type: {type(payload)!r}")
    return payload


class TushareHttpProvider:
    """CN MarketDataProvider via Tushare-compatible HTTP (``api_name`` style).

    First slice: ``daily`` (``api_name=daily``, unadjusted). Also exposes
    ``get_trade_cal`` for ops/calendar helpers (not a capability-matrix id).
    """

    name = "tushare_http"

    def __init__(
        self,
        *,
        token: str | None = None,
        url: str | None = None,
        post_json: PostJson | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._token = resolve_tushare_token(token, env=env)
        self._url = resolve_tushare_url(url, env=env)
        self._post_json = post_json

    def _require_token(self) -> str:
        if not self._token:
            raise TushareHttpError(
                f"missing Tushare token; set {ENV_TUSHARE_TOKEN} "
                "(never commit the token to git)"
            )
        return self._token

    def call(
        self,
        api_name: str,
        params: dict[str, Any] | None = None,
        *,
        fields: str = "",
    ) -> list[dict[str, Any]]:
        """POST ``{api_name, token, params, fields}`` and return row dicts."""
        token = self._require_token()
        body = {
            "api_name": api_name,
            "token": token,
            "params": params or {},
            "fields": fields,
        }
        if self._post_json is not None:
            payload = self._post_json(self._url, body)
        else:
            payload = _default_post_json(self._url, body)
        code = payload.get("code", payload.get("error_code"))
        if code not in (0, "0", None):
            msg = payload.get("msg") or payload.get("error_msg") or "unknown error"
            raise TushareHttpError(f"Tushare api_name={api_name!r} code={code}: {msg}")
        data = payload.get("data")
        if isinstance(data, dict):
            return rows_from_tushare_data(data)
        return []

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Fetch unadjusted daily bars via ``api_name=daily`` (pro_bar-equivalent)."""
        start_s = (start or date(1990, 1, 1)).strftime("%Y%m%d")
        end_s = (end or date(2099, 12, 31)).strftime("%Y%m%d")
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            ts_code = to_ts_code(code)
            items = self.call(
                "daily",
                {
                    "ts_code": ts_code,
                    "start_date": start_s,
                    "end_date": end_s,
                },
                fields=_DAILY_FIELDS,
            )
            for item in items:
                # Tushare amount is 千元 → platform 元; vol already 手.
                amount = item.get("amount")
                try:
                    amount_yuan = float(amount) * 1000.0 if amount not in (None, "") else None
                except (TypeError, ValueError):
                    amount_yuan = None
                pct = item.get("pct_chg")
                raw = {
                    "symbol": code,
                    "trade_date": item.get("trade_date"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "pre_close": item.get("pre_close"),
                    "volume": item.get("vol"),
                    "amount": amount_yuan,
                    "change_pct": pct,
                    "pct_unit": "percent" if pct not in (None, "") else None,
                }
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
        rows.sort(key=lambda r: (r["symbol"], r["date"]))
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        """Not mapped in first slice — fail closed."""
        raise NotImplementedError(
            "tushare_http does not provide realtime in v3.10; "
            "use astock_http or apply cn_astock_http preset"
        )

    def get_trade_cal(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        exchange: str = "SSE",
        is_open: str | None = "1",
    ) -> list[dict[str, Any]]:
        """Fetch exchange calendar via ``api_name=trade_cal`` (helper, not matrix cap)."""
        params: dict[str, Any] = {"exchange": exchange}
        if start is not None:
            params["start_date"] = start.strftime("%Y%m%d")
        if end is not None:
            params["end_date"] = end.strftime("%Y%m%d")
        if is_open is not None:
            params["is_open"] = is_open
        items = self.call(
            "trade_cal",
            params,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        out: list[dict[str, Any]] = []
        for item in items:
            cal = item.get("cal_date")
            if cal is None:
                continue
            text = str(cal).strip()
            if len(text) == 8 and text.isdigit():
                cal_iso = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
            else:
                cal_iso = text[:10]
            out.append(
                {
                    "exchange": item.get("exchange") or exchange,
                    "cal_date": cal_iso,
                    "is_open": str(item.get("is_open", "")),
                    "pretrade_date": item.get("pretrade_date"),
                }
            )
        return out
