"""U3 skeleton review helpers (deterministic; no public net)."""

from __future__ import annotations

import pytest

from stock_platform_research.brief_review import review_stored_brief


def test_review_stored_brief_settles_t1() -> None:
    record = {
        "asof": "2026-09-01",
        "picks": [{"rank": 1, "symbol": "AAA", "composite_score": 1.0}],
    }

    def get_daily(symbols, *, start, end):
        assert symbols == ["AAA"]
        return [
            {"date": "2026-09-01", "close": 10.0},
            {"date": "2026-09-02", "close": 11.0},
            {"date": "2026-09-03", "close": 12.0},
        ]

    out = review_stored_brief(record, get_daily=get_daily, holding="1d")
    assert out["settledCount"] == 1
    assert out["pendingCount"] == 0
    assert out["rows"][0]["pending"] is False
    assert out["rows"][0]["directionOk"] is True
    assert out["rows"][0]["rawReturnFloat"] == pytest.approx(0.1)
    assert out["direction_accuracy"] == pytest.approx(1.0)
    assert out["directionAccuracy"] == out["direction_accuracy"]
    assert "todo" not in out


def test_review_pending_when_no_bars() -> None:
    record = {"asof": "2026-09-01", "picks": [{"symbol": "BBB"}]}

    def get_daily(symbols, *, start, end):
        return [{"date": "2026-09-01", "close": 10.0}]

    out = review_stored_brief(record, get_daily=get_daily, holding="1d")
    assert out["pendingCount"] == 1
    assert out["rows"][0]["pending"] is True
    assert "不足" in (out["rows"][0]["note"] or "")
