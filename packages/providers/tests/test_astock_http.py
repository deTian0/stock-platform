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


def test_minute_from_klines() -> None:
    def get_json(url, params=None):
        assert "push2his" in url
        assert "kline/get" in url
        assert params["secid"] == "1.600519"
        assert params["klt"] == "1"
        return {
            "data": {
                "klines": [
                    "2026-09-01 09:31,1400.0,1401.0,1402.0,1399.5,1200,168120000",
                    "2026-09-01 09:32,1401.0,1402.5,1403.5,1400.5,980,137445000",
                ]
            }
        }

    rows = AStockHttpProvider(get_json=get_json).get_minute(
        ["SH600519"], freq="1m", start=date(2026, 9, 1), end=date(2026, 9, 1)
    )
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "astock_http"
    assert rows[0]["freq"] == "1m"
    assert rows[0]["datetime"] == "2026-09-01 09:31:00"
    assert rows[0]["close"] == 1401.0
    assert "+" not in rows[0]["datetime"]
    assert "Z" not in rows[0]["datetime"]


def test_minute_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"data": {}})
    with pytest.raises(SymbolError):
        provider.get_minute(["00700"])


def test_minute_empty_klines() -> None:
    rows = AStockHttpProvider(get_json=lambda *a, **k: {"data": {"klines": []}}).get_minute(
        ["600519"], freq="5m"
    )
    assert rows == []


def test_lhb_from_datacenter() -> None:
    calls: list[str] = []

    def get_json(url, params=None):
        assert "datacenter-web.eastmoney.com" in url
        report = (params or {}).get("reportName", "")
        calls.append(report)
        if report == "RPT_DAILYBILLBOARD_DETAILSNEW":
            return {
                "result": {
                    "data": [
                        {
                            "TRADE_DATE": "2026-05-16 00:00:00",
                            "EXPLANATION": "日涨幅偏离值达到7%",
                            "BILLBOARD_NET_AMT": 85200000.0,
                            "TURNOVERRATE": 12.34,
                        }
                    ]
                }
            }
        if report == "RPT_BILLBOARD_DAILYDETAILSBUY":
            return {
                "result": {
                    "data": [
                        {
                            "OPERATEDEPT_NAME": "机构专用",
                            "OPERATEDEPT_CODE": "0",
                            "BUY": 50000000.0,
                            "SELL": 0.0,
                            "NET": 50000000.0,
                        },
                        {
                            "OPERATEDEPT_NAME": "华泰证券上海分公司",
                            "OPERATEDEPT_CODE": "123",
                            "BUY": 32000000.0,
                            "SELL": 1000000.0,
                            "NET": 31000000.0,
                        },
                    ]
                }
            }
        if report == "RPT_BILLBOARD_DAILYDETAILSSELL":
            return {
                "result": {
                    "data": [
                        {
                            "OPERATEDEPT_NAME": "中信证券深圳分公司",
                            "OPERATEDEPT_CODE": "456",
                            "BUY": 0.0,
                            "SELL": 28000000.0,
                            "NET": -28000000.0,
                        }
                    ]
                }
            }
        return {"result": {"data": []}}

    items = AStockHttpProvider(get_json=get_json).get_lhb(
        ["SZ002475"], asof_date=date(2026, 5, 17), look_back_days=30
    )
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "002475"
    assert item["source"] == "astock_http"
    assert len(item["records"]) == 1
    assert item["records"][0]["net_buy"] == 85200000.0
    assert abs(item["records"][0]["turnover_rate"] - 0.1234) < 1e-6
    assert item["seats"]["buy"][0]["name"] == "机构专用"
    assert item["institution"]["buy_amt"] == 50000000.0
    assert item["institution"]["net_amt"] == 50000000.0
    assert calls == [
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        "RPT_BILLBOARD_DAILYDETAILSBUY",
        "RPT_BILLBOARD_DAILYDETAILSSELL",
    ]


def test_lhb_empty_window() -> None:
    def get_json(url, params=None):
        return {"result": {"data": []}}

    items = AStockHttpProvider(get_json=get_json).get_lhb(
        ["600519"], asof_date=date(2026, 5, 17)
    )
    assert len(items) == 1
    assert items[0]["records"] == []
    assert items[0]["seats"] == {"buy": [], "sell": []}
    assert items[0]["institution"]["net_amt"] == 0.0


def test_lhb_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"result": {"data": []}})
    with pytest.raises(SymbolError):
        provider.get_lhb(["00700"], asof_date=date(2026, 5, 17))


def test_unlock_from_datacenter() -> None:
    calls: list[str] = []
    filters: list[str] = []

    def get_json(url, params=None):
        assert "datacenter-web.eastmoney.com" in url
        report = (params or {}).get("reportName", "")
        calls.append(report)
        filters.append((params or {}).get("filter", ""))
        filt = (params or {}).get("filter", "")
        if "FREE_DATE>=" in filt:
            return {
                "result": {
                    "data": [
                        {
                            "FREE_DATE": "2026-07-01 00:00:00",
                            "FREE_SHARES_TYPE": "首发原股东限售股份",
                            "FREE_SHARES": 32000.0,
                            "ABLE_FREE_SHARES": 28000.0,
                            "FREE_RATIO": 0.0456,
                        }
                    ]
                }
            }
        return {
            "result": {
                "data": [
                    {
                        "FREE_DATE": "2025-11-20 00:00:00",
                        "FREE_SHARES_TYPE": "定向增发机构配售股份",
                        "FREE_SHARES": 8500.0,
                        "ABLE_FREE_SHARES": 8500.0,
                        "FREE_RATIO": 0.0123,
                    }
                ]
            }
        }

    items = AStockHttpProvider(get_json=get_json).get_unlock(
        ["SZ002475"], asof_date=date(2026, 5, 17), forward_days=90
    )
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "002475"
    assert item["source"] == "astock_http"
    assert item["forward_days"] == 90
    assert len(item["history"]) == 1
    assert item["history"][0]["shares"] == 8500.0
    assert len(item["upcoming"]) == 1
    assert item["upcoming"][0]["able_shares"] == 28000.0
    assert calls == ["RPT_LIFT_STAGE", "RPT_LIFT_STAGE"]
    assert "FREE_DATE>=" in filters[1]


def test_unlock_empty_window() -> None:
    def get_json(url, params=None):
        return {"result": {"data": []}}

    items = AStockHttpProvider(get_json=get_json).get_unlock(
        ["600519"], asof_date=date(2026, 5, 17)
    )
    assert len(items) == 1
    assert items[0]["history"] == []
    assert items[0]["upcoming"] == []


def test_unlock_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"result": {"data": []}})
    with pytest.raises(SymbolError):
        provider.get_unlock(["00700"], asof_date=date(2026, 5, 17))
