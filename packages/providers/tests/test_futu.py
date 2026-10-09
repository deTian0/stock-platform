"""Tests for the 富途 (Futu) OpenAPI provider (fake module + fake context, zero network)."""

from __future__ import annotations

import types
from datetime import date

import pandas as pd
import pytest

from stock_platform_providers.futu import FutuProvider


def _fake_futu():
    return types.SimpleNamespace(
        KLType=types.SimpleNamespace(K_DAY="K_DAY"),
        AuType=types.SimpleNamespace(QFQ="QFQ"),
        RET_OK=0,
    )


class _FakeQuoteCtx:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request_history_kline(self, code, **kwargs):
        self.calls.append(f"kline:{code}")
        df = pd.DataFrame(
            [
                {"time_key": "2026-01-02 00:00:00", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 5000, "turnover": 1_000_000},
                {"time_key": "2026-01-03 00:00:00", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 5200, "turnover": 1_200_000},
            ]
        )
        return (0, df, None)

    def get_market_snapshot(self, code_list):
        self.calls.append(f"snap:{','.join(code_list)}")
        df = pd.DataFrame(
            [
                {"code": "SH.600519", "name": "贵州茅台", "last_price": 105.0, "prev_close_price": 102.0, "price_change": 3.0, "price_change_rate": 0.029, "volume": 5000, "turnover": 1_000_000, "update_time": "2026-01-03 15:00:00"},
            ]
        )
        return (0, df)


def _provider():
    return FutuProvider(quote_ctx=_FakeQuoteCtx(), futu_module=_fake_futu())


def test_get_daily_normalizes(tmp_path) -> None:
    p = _provider()
    rows = p.get_daily(["600519"])
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["date"] == "2026-01-02"
    assert rows[0]["close"] == 101.0
    assert rows[0]["source"] == "futu"


def test_get_daily_maps_exchange() -> None:
    p = _provider()
    p.get_daily(["000001"])
    assert p._quote_ctx.calls[0] == "kline:SZ.000001"


def test_get_daily_date_filter() -> None:
    p = _provider()
    rows = p.get_daily(["600519"], start=date(2026, 1, 3))
    assert [r["date"] for r in rows] == ["2026-01-03"]


def test_get_realtime_normalizes() -> None:
    p = _provider()
    rows = p.get_realtime(["600519"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["price"] == 105.0
    assert rows[0]["source"] == "futu"


def test_no_sdk_fails_closed() -> None:
    # No futu_module, no quote_ctx → _import_futu raises (futu not installed in CI).
    p = FutuProvider()
    with pytest.raises(RuntimeError):
        p.get_daily(["600519"])
