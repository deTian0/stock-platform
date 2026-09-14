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


def test_depth5_from_quote() -> None:
    def get_json(url, params=None):
        assert "push2.eastmoney.com" in url
        assert "stock/get" in url
        assert params["secid"] == "1.600519"
        assert "f19" in params["fields"]
        assert "f39" in params["fields"]
        return {
            "data": {
                "f19": 1425.0,
                "f20": 10,
                "f17": 1424.9,
                "f18": 20,
                "f15": 1424.8,
                "f16": 30,
                "f13": 1424.7,
                "f14": 40,
                "f11": 1424.6,
                "f12": 50,
                "f39": 1425.1,
                "f40": 12,
                "f37": 1425.2,
                "f38": 22,
                "f35": 1425.3,
                "f36": 32,
                "f33": 1425.4,
                "f34": 42,
                "f31": 1425.5,
                "f32": 52,
                "f86": 1725260400000,
            }
        }

    rows = AStockHttpProvider(get_json=get_json).get_depth5(["SH600519"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "astock_http"
    assert rows[0]["bid_prices"] == [1425.0, 1424.9, 1424.8, 1424.7, 1424.6]
    assert rows[0]["ask_volumes"] == [12.0, 22.0, 32.0, 42.0, 52.0]
    assert rows[0]["asof_ts"] == 1725260400000


def test_depth5_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"data": {}})
    with pytest.raises(SymbolError):
        provider.get_depth5(["00700"])


def test_depth5_empty_data() -> None:
    rows = AStockHttpProvider(get_json=lambda *a, **k: {"data": {}}).get_depth5(["600519"])
    assert rows == []


def test_financial_from_sina() -> None:
    calls: list[str] = []

    def get_json(url, params=None):
        assert "quotes.sina.cn" in url
        assert "CompanyFinanceService" in url
        source = (params or {}).get("source")
        calls.append(source)
        period = "20260331"
        titles = {
            "lrb": [
                {"item_title": "营业收入", "item_value": "39112000000"},
                {"item_title": "净利润", "item_value": "20850000000"},
                {"item_title": "归属于母公司所有者的净利润", "item_value": "20800000000"},
                {"item_title": "基本每股收益", "item_value": "16.57"},
            ],
            "fzb": [
                {"item_title": "资产总计", "item_value": "310000000000"},
                {"item_title": "负债合计", "item_value": "48000000000"},
                {"item_title": "所有者权益合计", "item_value": "262000000000"},
            ],
            "llb": [
                {"item_title": "经营活动产生的现金流量净额", "item_value": "22000000000"},
                {"item_title": "投资活动产生的现金流量净额", "item_value": "-1500000000"},
                {"item_title": "筹资活动产生的现金流量净额", "item_value": "-18000000000"},
            ],
        }
        return {
            "result": {
                "data": {
                    "report_list": {
                        period: {"data": titles[source]},
                    }
                }
            }
        }

    items = AStockHttpProvider(get_json=get_json).get_financial(["SH600519"], periods=1)
    assert calls == ["lrb", "fzb", "llb"]
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "600519"
    assert item["source"] == "astock_http"
    assert item["periods"] == 1
    assert item["income"][0]["revenue"] == 39112000000.0
    assert item["balance"][0]["total_equity"] == 262000000000.0
    assert item["cashflow"][0]["net_financing_cash_flow"] == -18000000000.0


def test_financial_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {})
    with pytest.raises(SymbolError):
        provider.get_financial(["00700"])


def test_financial_empty_reports() -> None:
    items = AStockHttpProvider(
        get_json=lambda *a, **k: {"result": {"data": {"report_list": {}}}}
    ).get_financial(["600519"])
    assert items == []


def test_adj_factor_from_sina_js() -> None:
    def get_text(url: str) -> str:
        assert "finance.sina.com.cn/realstock/company/sh600519/qfq.js" in url
        # Trailing base64 comment must not break raw_decode
        return (
            'var sh600519qfq={"data":[{"d":"2026-06-26","f":"1.0000"},'
            '{"d":"2015-01-05","f":"1.4118"}]};/* base64 junk */'
        )

    rows = AStockHttpProvider(get_text=get_text).get_adj_factor(["SH600519"])
    assert len(rows) == 2
    assert rows[0]["symbol"] == "600519"
    assert rows[0]["source"] == "astock_http"
    assert rows[0]["trade_date"] == "2026-06-26"
    assert rows[0]["ex_factor"] == 1.0
    assert rows[1]["trade_date"] == "2015-01-05"
    assert rows[1]["ex_factor"] == 1.4118


def test_adj_factor_rejects_hk() -> None:
    provider = AStockHttpProvider(get_text=lambda *a, **k: "")
    with pytest.raises(SymbolError):
        provider.get_adj_factor(["00700"])


def test_adj_factor_empty_data() -> None:
    rows = AStockHttpProvider(
        get_text=lambda *a, **k: 'var x={"data":[]};'
    ).get_adj_factor(["600519"])
    assert rows == []


def test_adj_factor_invalid_kind() -> None:
    provider = AStockHttpProvider(get_text=lambda *a, **k: "")
    with pytest.raises(ValueError, match="qfq"):
        provider.get_adj_factor(["600519"], kind="bad")


def test_full_minute_from_kline() -> None:
    def get_json(url, params=None):
        assert "push2his.eastmoney.com" in url
        assert params["klt"] == "1"
        assert params["beg"] == "20260901"
        assert params["end"] == "20260901"
        assert params["secid"] == "1.600519"
        return {
            "data": {
                "klines": [
                    "2026-09-01 09:31,1400.0,1401.0,1402.0,1399.5,1200,168120000",
                    "2026-09-01 09:32,1401.0,1402.5,1403.5,1400.5,980,137445000",
                ]
            }
        }

    rows = AStockHttpProvider(get_json=get_json).get_full_minute(
        ["SH600519"], trade_date=date(2026, 9, 1), count=300
    )
    assert len(rows) == 2
    assert rows[0]["freq"] == "1m"
    assert rows[0]["source"] == "astock_http"
    assert rows[0]["datetime"] == "2026-09-01 09:31:00"


def test_full_minute_rejects_hk() -> None:
    provider = AStockHttpProvider(get_json=lambda *a, **k: {"data": {}})
    with pytest.raises(SymbolError):
        provider.get_full_minute(["00700"], trade_date=date(2026, 9, 1))


def test_full_minute_empty_klines() -> None:
    rows = AStockHttpProvider(get_json=lambda *a, **k: {"data": {"klines": []}}).get_full_minute(
        ["600519"], trade_date=date(2026, 9, 1)
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
