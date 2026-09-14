"""GlobalHttpProvider tests — mocked Yahoo JSON / Sina text only (no network)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from stock_platform_providers import SymbolError
from stock_platform_providers.global_http import (
    GlobalHttpProvider,
    GlobalHttpRouter,
    infer_global_market,
    parse_sina_quote_text,
    parse_yahoo_chart,
    sina_list_id,
    yahoo_symbol,
)


def test_yahoo_and_sina_ids() -> None:
    assert yahoo_symbol("AAPL", market="US") == "AAPL"
    assert yahoo_symbol("00700", market="HK") == "00700.HK"
    assert sina_list_id("AAPL", market="US") == "gb_aapl"
    assert sina_list_id("00700", market="HK") == "rt_hk00700"


def test_infer_global_market() -> None:
    assert infer_global_market("AAPL") == "US"
    assert infer_global_market("0700.HK") == "HK"
    assert infer_global_market("00700") == "HK"
    with pytest.raises(SymbolError):
        infer_global_market("600519")


def test_parse_yahoo_chart_skips_null_close() -> None:
    ts = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    rows = parse_yahoo_chart(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [ts, ts + 86400],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [100.0, None],
                                    "high": [101.0, None],
                                    "low": [99.0, None],
                                    "close": [100.5, None],
                                    "volume": [1_000_000, None],
                                }
                            ]
                        },
                    }
                ]
            }
        }
    )
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-09-01"
    assert rows[0]["close"] == 100.5


def test_us_daily_from_yahoo() -> None:
    ts1 = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    ts2 = int(datetime(2026, 9, 2, tzinfo=timezone.utc).timestamp())

    def get_json(url, params=None):
        assert "finance.yahoo.com" in url
        assert "AAPL" in url
        assert params["interval"] == "1d"
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": [ts1, ts2],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [220.0, 225.0],
                                    "high": [222.0, 228.0],
                                    "low": [219.0, 224.0],
                                    "close": [221.0, 227.0],
                                    "volume": [10, 12],
                                }
                            ]
                        },
                    }
                ]
            }
        }

    rows = GlobalHttpProvider(market="US", get_json=get_json).get_daily(
        ["aapl"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[-1]["symbol"] == "AAPL"
    assert rows[-1]["close"] == 227.0
    assert rows[-1]["source"] == "global_http"


def test_hk_realtime_from_sina() -> None:
    # 15+ fields per Skill; indices 1..8, 11, 12 used
    fields = [""] * 15
    fields[0] = "TENCENT"
    fields[1] = "腾讯控股"
    fields[2] = "390"
    fields[3] = "391"
    fields[4] = "395"
    fields[5] = "388"
    fields[6] = "392"
    fields[7] = "1"
    fields[8] = "0.255"
    fields[11] = "1.2e9"
    fields[12] = "2.5e7"
    payload = ",".join(fields)

    def get_text(url):
        assert "rt_hk00700" in url
        return f'var hq_str_rt_hk00700="{payload}";\n'

    rows = GlobalHttpProvider(market="HK", get_text=get_text).get_realtime(["0700.HK"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "00700"
    assert rows[0]["price"] == 392.0
    assert abs(rows[0]["change_pct"] - 0.00255) < 1e-6


def test_us_realtime_from_sina() -> None:
    # Minimal 30+ fields; indices used: 0,1,2,5,6,7,10,26
    fields = [""] * 30
    fields[0] = "苹果"
    fields[1] = "227.0"
    fields[2] = "1.5"
    fields[5] = "225.0"
    fields[6] = "228.0"
    fields[7] = "224.0"
    fields[10] = "1000"
    fields[26] = "223.0"
    payload = ",".join(fields)

    def get_text(url):
        assert "gb_aapl" in url
        return f'var hq_str_gb_aapl="{payload}";'

    rows = GlobalHttpProvider(market="US", get_text=get_text).get_realtime(["AAPL"])
    assert rows[0]["price"] == 227.0
    assert abs(rows[0]["change_pct"] - 0.015) < 1e-6


def test_us_provider_rejects_hk() -> None:
    with pytest.raises(SymbolError):
        GlobalHttpProvider(market="US", get_json=lambda *a, **k: {}).get_daily(["00700"])


def test_router_splits_markets() -> None:
    ts = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())

    def get_json(url, params=None):
        close = 227.0 if "AAPL" in url else 392.0
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": [ts],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [close],
                                    "high": [close],
                                    "low": [close],
                                    "close": [close],
                                    "volume": [1],
                                }
                            ]
                        },
                    }
                ]
            }
        }

    router = GlobalHttpRouter(get_json=get_json, get_text=lambda u: "")
    rows = router.get_daily(["AAPL", "00700"], start=date(2026, 9, 1), end=date(2026, 9, 1))
    assert [r["symbol"] for r in rows] == ["AAPL", "00700"]
    assert rows[0]["close"] == 227.0
    assert rows[1]["close"] == 392.0


def test_parse_sina_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_sina_quote_text("var hq_str_gb_aapl=\"\";", market="US")
