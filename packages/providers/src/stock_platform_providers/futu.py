"""富途 (Futu) OpenAPI adapter — lazy ``futu`` import, OpenD gateway.

The ``futu`` SDK is **not** a hard dependency: it is imported lazily and the
provider fails closed (Chinese message) when the package or the OpenD gateway
(``127.0.0.1:11111`` by default) is unavailable. Symbol mapping uses the same
``exchange_prefix`` authority as the rest of the CN surface (``SH.``/``SZ.``/``BJ.``).
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from .base import AssetType
from .normalize import normalize_daily_row, normalize_realtime_row
from .symbol import exchange_prefix, normalize_symbol

ENV_FUTU_HOST = "STOCK_PLATFORM_FUTU_HOST"
ENV_FUTU_PORT = "STOCK_PLATFORM_FUTU_PORT"
DEFAULT_FUTU_HOST = "127.0.0.1"
DEFAULT_FUTU_PORT = 11111
PROVIDER_NAME = "futu"

MSG_NO_SDK = (
    "未安装 futu-api：请 `pip install futu-api` 并启动富途 OpenD 网关后再用 "
    "cn_futu 预设；平台不自动安装、不静默回退其它源。"
)
MSG_NO_GATEWAY = (
    "无法连接富途 OpenD 网关（{host}:{port}）：请先启动 FutuOpenD 并登录，"
    "或通过 STOCK_PLATFORM_FUTU_HOST / STOCK_PLATFORM_FUTU_PORT 指定地址。"
)


def _futu_code(code: str) -> str:
    prefix = exchange_prefix(code)
    suffix = {"sh": "SH", "sz": "SZ", "bj": "BJ"}[prefix]
    return f"{suffix}.{code}"


def _import_futu() -> Any:
    try:
        import futu  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on host env
        raise RuntimeError(MSG_NO_SDK) from exc
    return futu


class FutuProvider:
    """CN MarketDataProvider via Futu OpenAPI (OpenD)."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        quote_ctx: Any | None = None,
        futu_module: Any | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        source = env if env is not None else os.environ
        self._host = host or str(source.get(ENV_FUTU_HOST, "") or DEFAULT_FUTU_HOST)
        raw_port = port if port is not None else int(source.get(ENV_FUTU_PORT, "") or DEFAULT_FUTU_PORT)
        self._port = raw_port
        # Inject a fake context + module in tests (no SDK / no gateway needed).
        self._quote_ctx = quote_ctx
        self._futu_module = futu_module

    def _mod(self) -> Any:
        return self._futu_module if self._futu_module is not None else _import_futu()

    def _ctx(self) -> Any:
        if self._quote_ctx is not None:
            return self._quote_ctx
        futu = self._mod()
        try:
            return futu.OpenQuoteContext(host=self._host, port=self._port)
        except Exception as exc:  # pragma: no cover - depends on host env
            raise RuntimeError(
                MSG_NO_GATEWAY.format(host=self._host, port=self._port)
            ) from exc

    def _kline(self, futu: Any, ctx: Any, code: str, start: str, end: str) -> Any:
        ret, data, _ = ctx.request_history_kline(
            code,
            start=start,
            end=end,
            ktype=futu.KLType.K_DAY,
            autype=futu.AuType.QFQ,
            max_count=10000,
        )
        if ret != futu.RET_OK:
            raise RuntimeError(f"futu request_history_kline({code}) failed: {data}")
        return data

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        futu = self._mod()
        ctx = self._ctx()
        start_s = (start or date(1990, 1, 1)).strftime("%Y-%m-%d")
        end_s = (end or date(2099, 12, 31)).strftime("%Y-%m-%d")
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            data = self._kline(futu, ctx, _futu_code(code), start_s, end_s)
            if data is None or getattr(data, "empty", True):
                continue
            for _, rec in data.iterrows():
                raw = {
                    "symbol": code,
                    "date": str(rec.get("time_key"))[:10],
                    "open": rec.get("open"),
                    "high": rec.get("high"),
                    "low": rec.get("low"),
                    "close": rec.get("close"),
                    "volume": rec.get("volume"),
                    "amount": rec.get("turnover"),
                }
                try:
                    row = normalize_daily_row(
                        raw,
                        source=self.name,
                        asset_type=asset_type,
                        default_symbol=code,
                        market="CN",
                    )
                except ValueError:
                    continue
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
        futu = self._mod()
        ctx = self._ctx()
        code_list = [_futu_code(normalize_symbol(s, market="CN")) for s in symbols]
        ret, data = ctx.get_market_snapshot(code_list)
        if ret != futu.RET_OK:
            raise RuntimeError(f"futu get_market_snapshot failed: {data}")
        rows: list[dict[str, Any]] = []
        if data is None or getattr(data, "empty", True):
            return rows
        for _, rec in data.iterrows():
            raw_code = str(rec.get("code") or "")
            code = raw_code.split(".")[-1]
            raw = {
                "symbol": code,
                "name": rec.get("name"),
                "price": rec.get("last_price"),
                "prev_close": rec.get("prev_close_price"),
                "change_amount": rec.get("price_change"),
                "change_pct": rec.get("price_change_rate"),
                "volume": rec.get("volume"),
                "amount": rec.get("turnover"),
                "asof_ts": rec.get("update_time"),
            }
            try:
                rows.append(
                    normalize_realtime_row(
                        raw,
                        source=self.name,
                        asset_type=asset_type,
                        default_symbol=code,
                        market="CN",
                    )
                )
            except ValueError:
                continue
        return rows
