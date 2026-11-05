"""S2-P1 market-wide day cross-sections on AStockHttpProvider (mocked JSON, no network)."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_providers.astock_http import (
    BOARD_RANK_URL,
    DATACENTER_URL,
    AStockHttpProvider,
)


def test_lhb_daily_one_page_market_wide() -> None:
    calls: list[dict] = []

    def get_json(url, params=None):
        assert url == DATACENTER_URL
        calls.append(dict(params or {}))
        assert params["reportName"] == "RPT_DAILYBILLBOARD_DETAILSNEW"
        assert params["filter"] == "(TRADE_DATE='2026-11-05')"
        assert "SECURITY_CODE=" not in params["filter"]
        return {
            "result": {
                "pages": 1,
                "data": [
                    {
                        "TRADE_DATE": "2026-11-05 00:00:00",
                        "SECURITY_CODE": "002086",
                        "SECURITY_NAME_ABBR": "东方海洋",
                        "EXPLANATION": "日涨幅偏离值达到7%的前5只证券",
                        "BILLBOARD_NET_AMT": 100422374.48,
                        "BILLBOARD_BUY_AMT": 367015789.98,
                        "BILLBOARD_SELL_AMT": 266593415.5,
                        "CHANGE_RATE": 10.061,
                        "TURNOVERRATE": 53.0025,
                    },
                    # Stray other-day row must be dropped (strict asof).
                    {"TRADE_DATE": "2026-11-04 00:00:00", "SECURITY_CODE": "600000"},
                ],
            }
        }

    out = AStockHttpProvider(get_json=get_json).get_lhb_daily(date(2026, 11, 5))
    assert len(calls) == 1
    assert out["trade_date"] == "2026-11-05"
    assert out["truncated"] is False
    assert [r["symbol"] for r in out["records"]] == ["002086"]
    rec = out["records"][0]
    assert rec["net_buy"] == pytest.approx(100422374.48)
    assert rec["change_pct"] == pytest.approx(0.10061)  # decimal
    assert rec["turnover_rate"] == pytest.approx(0.530025)


def test_lhb_daily_pagination_capped_and_flagged() -> None:
    pages_seen: list[str] = []

    def get_json(url, params=None):
        pages_seen.append(params["pageNumber"])
        return {
            "result": {
                "pages": 9,
                "data": [{"TRADE_DATE": "2026-11-05", "SECURITY_CODE": f"60000{params['pageNumber']}"}],
            }
        }

    out = AStockHttpProvider(get_json=get_json).get_lhb_daily(date(2026, 11, 5), max_pages=2)
    assert pages_seen == ["1", "2"]
    assert out["truncated"] is True
    assert len(out["records"]) == 2


def test_unlock_calendar_window() -> None:
    def get_json(url, params=None):
        assert params["reportName"] == "RPT_LIFT_STAGE"
        assert params["filter"] == "(FREE_DATE>='2026-11-05')(FREE_DATE<='2026-12-05')"
        return {
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "920176",
                        "SECURITY_NAME_ABBR": "维琪科技",
                        "FREE_DATE": "2026-11-05 00:00:00",
                        "FREE_SHARES_TYPE": "公开发行原股东限售股份",
                        "FREE_SHARES": 1969.2985,
                        "ABLE_FREE_SHARES": 1174.5985,
                        "FREE_RATIO": 0.596455285981,
                    }
                ],
            }
        }

    out = AStockHttpProvider(get_json=get_json).get_unlock_calendar(
        date(2026, 11, 5), date(2026, 12, 5)
    )
    assert out["events"][0]["symbol"] == "920176"
    assert out["events"][0]["date"] == "2026-11-05"
    assert out["events"][0]["ratio"] == pytest.approx(0.596455285981)


def test_board_rank_snapshot_fields() -> None:
    def get_json(url, params=None):
        assert url == BOARD_RANK_URL
        assert params["fs"] == "m:90+t:3"
        assert params["fid"] == "f62"
        return {
            "data": {
                "total": 531,
                "diff": [
                    {
                        "f3": 2.68,
                        "f12": "BK1005",
                        "f14": "专精特新",
                        "f62": 8047462144.0,
                        "f124": 1793864370,
                        "f128": "永臻股份",
                        "f140": "603381",
                    }
                ],
            }
        }

    out = AStockHttpProvider(get_json=get_json).get_board_rank("concept", limit=500)
    assert out["kind"] == "concept"
    assert out["updated_at"] and out["updated_at"].startswith("2026-")
    b = out["boards"][0]
    assert b["code"] == "BK1005"
    assert b["lead_stock"] == "603381"
    assert b["change_pct"] == pytest.approx(0.0268)


def test_board_rank_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        AStockHttpProvider(get_json=lambda *a, **k: {}).get_board_rank("region")
