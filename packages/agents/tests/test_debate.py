"""Deterministic debate scoring tests (no network / no LLM)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from stock_platform_agents import AgentError, build_debate_report
from stock_platform_agents.debate import _metrics, _score, _verdict


class _SeqProvider:
    name = "seq"

    def __init__(self, closes: list[float], *, start: date = date(2026, 1, 2)) -> None:
        self._closes = closes
        self._start = start

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: str = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        d = self._start
        for i, close in enumerate(self._closes):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            row_date = d
            d += timedelta(days=1)
            if start and row_date < start:
                continue
            if end and row_date > end:
                continue
            prev = self._closes[i - 1] if i else close
            rows.append(
                {
                    "symbol": "600519",
                    "date": row_date.isoformat(),
                    "close": close,
                    "open": prev,
                    "high": max(prev, close),
                    "low": min(prev, close),
                    "volume": 1000.0,
                    "change_pct": (close / prev - 1.0) if prev else 0.0,
                }
            )
        return rows

    def get_realtime(self, symbols: list[str], *, asset_type: str = "stock") -> list[dict[str, Any]]:
        raise RuntimeError("no realtime in seq fixture")


def test_rising_series_leans_buy() -> None:
    closes = [100 + i * 2 for i in range(20)]
    report = build_debate_report(_SeqProvider(closes), "600519", asof=date(2026, 2, 20))
    assert report.kind == "debate"
    assert report.verdict == "Buy"
    assert report.score["net"] > 0
    assert any(r.role == "bull" for r in report.rounds)
    assert "非投资建议" in report.disclaimer
    assert any("跳过 realtime" in w for w in report.warnings)


def test_falling_series_leans_sell() -> None:
    closes = [140 - i * 2 for i in range(20)]
    report = build_debate_report(_SeqProvider(closes), "600519", asof=date(2026, 2, 20))
    assert report.verdict == "Sell"
    assert report.score["net"] < 0
    assert any(r.role == "bear" for r in report.rounds)


def test_flat_series_hold() -> None:
    closes = [100.0] * 15
    report = build_debate_report(_SeqProvider(closes), "600519", asof=date(2026, 2, 10))
    assert report.verdict == "Hold"


def test_need_two_closes() -> None:
    with pytest.raises(AgentError):
        _metrics([100.0])


def test_score_verdict_thresholds() -> None:
    assert _verdict({"net": 1.0, "bull": 1, "bear": 0, "risk": 0}) == "Buy"
    assert _verdict({"net": -1.0, "bull": 0, "bear": 1, "risk": 0}) == "Sell"
    assert _verdict({"net": 0.0, "bull": 0, "bear": 0, "risk": 0}) == "Hold"
    s = _score(
        {
            "return": 0.1,
            "max_drawdown": -0.02,
            "vs_ma": 0.05,
            "vol": 0.01,
            "down_ratio": 0.2,
        }
    )
    assert s["bull"] > s["bear"]
