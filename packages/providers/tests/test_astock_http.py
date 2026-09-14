"""AStockHttpProvider tests — mocked EM JSON only (no network)."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_providers import SymbolError
from stock_platform_providers.astock_http import AStockHttpProvider, em_secid


def test_em_secid() -> None:
    assert em_secid("600519") == "1.600519"
    assert em_secid("000001") == "0.000001"
    assert em_secid("920001") == "0.920001"


def test_daily_from_klines() -> None:
    def get_json(url, params=None):
        assert "push2his" in url
        assert params["secid"] == "1.600519"
        return {
            "data": {
                "klines": [
                    "2026-09-01,1400.0,1410.0,1420.5,1395.0,25000,3525000000,1.8,0.356,5.0,0.12",
                    "2026-09-02,1410.0,1425.0,1430.0,1408.0,28000,3980000000,1.56,1.0638,15.0,0.13",
                ]
            }
        }

    provider = AStockHttpProvider(get_json=get_json)
    rows = provider.get_daily(
        ["SH600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "astock_http"
    assert rows[0]["close"] == 1410.0
    assert abs(rows[0]["change_pct"] - 0.00356) < 1e-6
    assert rows[1]["close"] == 1425.0


def test_realtime_from_push2() -> None:
    def get_json(url, params=None):
        assert "push2.eastmoney.com" in url
        return {
            "data": {
                "f43": 1425.0,
                "f57": "600519",
                "f58": "贵州茅台",
                "f60": 1410.0,
                "f169": 15.0,
                "f170": 1.0638,
                "f171": 1.56,
                "f168": 0.12,
                "f47": 28000,
                "f48": 3980000000,
                "f86": 1725260400000,
            }
        }

    rows = AStockHttpProvider(get_json=get_json).get_realtime(["600519"])
    assert len(rows) == 1
    assert rows[0]["price"] == 1425.0
    assert rows[0]["name"] == "贵州茅台"
    assert abs(rows[0]["change_pct"] - 0.010638) < 1e-6


def test_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"data": {}})
    with pytest.raises(SymbolError):
        provider.get_daily(["00700"])


def test_fund_flow_from_daykline() -> None:
    def get_json(url, params=None):
        assert "fflow/daykline" in url
        assert params["secid"] == "1.600519"
        return {
            "data": {
                "klines": [
                    "2026-09-01,125000000,-45000000,-30000000,80000000,45000000",
                    "2026-09-02,-82000000,22000000,15000000,-50000000,-32000000",
                ]
            }
        }

    rows = AStockHttpProvider(get_json=get_json).get_fund_flow(
        ["SH600519"], start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "astock_http"
    assert rows[0]["main_net"] == 125000000.0
    assert rows[0]["super_net"] == 45000000.0
    assert rows[1]["main_net"] == -82000000.0


def test_fund_flow_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"data": {}})
    with pytest.raises(SymbolError):
        provider.get_fund_flow(["00700"])
