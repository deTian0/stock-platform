"""TushareHttpProvider tests — mocked POST only (no network, no real token)."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_providers import SymbolError, TushareHttpError, TushareHttpProvider
from stock_platform_providers.tushare_http import (
    DEFAULT_TUSHARE_URL,
    from_ts_code,
    rows_from_tushare_data,
    to_ts_code,
)


def test_ts_code_roundtrip() -> None:
    assert to_ts_code("600519") == "600519.SH"
    assert to_ts_code("000001") == "000001.SZ"
    assert to_ts_code("920001") == "920001.BJ"
    assert from_ts_code("600519.SH") == "600519"
    assert from_ts_code("000001.SZ") == "000001"


def test_daily_from_api_name_payload() -> None:
    calls: list[dict] = []

    def post_json(url, body):
        calls.append({"url": url, "body": body})
        assert url == DEFAULT_TUSHARE_URL
        assert body["api_name"] == "daily"
        assert body["token"] == "test-token-not-real"
        assert body["params"]["ts_code"] == "600519.SH"
        return {
            "code": 0,
            "msg": "",
            "data": {
                "fields": [
                    "ts_code",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "pre_close",
                    "change",
                    "pct_chg",
                    "vol",
                    "amount",
                ],
                "items": [
                    [
                        "600519.SH",
                        "20260901",
                        1400.0,
                        1420.5,
                        1395.0,
                        1410.0,
                        1405.0,
                        5.0,
                        0.356,
                        25000.0,
                        3525000.0,  # 千元 → 元 *1000
                    ],
                    [
                        "600519.SH",
                        "20260902",
                        1410.0,
                        1430.0,
                        1408.0,
                        1425.0,
                        1410.0,
                        15.0,
                        1.0638,
                        28000.0,
                        3980000.0,
                    ],
                ],
            },
        }

    provider = TushareHttpProvider(token="test-token-not-real", post_json=post_json)
    rows = provider.get_daily(
        ["SH600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "tushare_http"
    assert rows[0]["close"] == 1410.0
    assert rows[0]["amount"] == 3525000.0 * 1000.0
    assert abs(rows[0]["change_pct"] - 0.00356) < 1e-6
    assert rows[1]["close"] == 1425.0
    assert len(calls) == 1


def test_trade_cal_from_payload() -> None:
    def post_json(url, body):
        assert body["api_name"] == "trade_cal"
        assert body["params"]["exchange"] == "SSE"
        return {
            "code": 0,
            "data": {
                "fields": ["exchange", "cal_date", "is_open", "pretrade_date"],
                "items": [
                    ["SSE", "20260901", "1", "20260829"],
                    ["SSE", "20260902", "1", "20260901"],
                ],
            },
        }

    rows = TushareHttpProvider(token="test-token-not-real", post_json=post_json).get_trade_cal(
        start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["cal_date"] == "2026-09-01"
    assert rows[0]["is_open"] == "1"


def test_missing_token_fails_closed() -> None:
    provider = TushareHttpProvider(token="", env={})
    with pytest.raises(TushareHttpError, match="STOCK_PLATFORM_TUSHARE_TOKEN"):
        provider.get_daily(["600519"])


def test_upstream_error_code() -> None:
    def post_json(url, body):
        return {"code": 40101, "msg": "token invalid (fixture)"}

    provider = TushareHttpProvider(token="bad", post_json=post_json)
    with pytest.raises(TushareHttpError, match="40101"):
        provider.get_daily(["600519"])


def test_rejects_hk() -> None:
    provider = TushareHttpProvider(
        token="x", post_json=lambda *a, **k: {"code": 0, "data": {"fields": [], "items": []}}
    )
    with pytest.raises(SymbolError):
        provider.get_daily(["00700"])


def test_realtime_not_implemented() -> None:
    provider = TushareHttpProvider(token="x")
    with pytest.raises(NotImplementedError):
        provider.get_realtime(["600519"])


def test_rows_from_tushare_data_empty() -> None:
    assert rows_from_tushare_data(None) == []
    assert rows_from_tushare_data({}) == []
