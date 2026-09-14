"""Optional LLM debate tests — mocked client; no network / no API key required."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from stock_platform_agents.llm_debate import (
    LlmBudgetExceeded,
    LlmUnavailableError,
    debate_brief_picks,
    llm_debate_status,
    run_debate,
    warn_if_truncated,
)


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
        raise RuntimeError("no realtime")


def _fake_llm(system: str, user: str) -> str:
    return (
        '{"bull":"momentum","bear":"drawdown","risk":"vol",'
        '"verdict":"Buy","judge":"mock buy"}'
    )


def test_default_engine_is_deterministic() -> None:
    closes = [100 + i for i in range(20)]
    report = run_debate(_SeqProvider(closes), "600519", asof=date(2026, 2, 20))
    assert report.kind == "debate"
    assert "未调用 LLM" in report.disclaimer


def test_llm_engine_with_mock() -> None:
    closes = [100 + i for i in range(20)]
    report = run_debate(
        _SeqProvider(closes),
        "600519",
        asof=date(2026, 2, 20),
        engine="llm",
        llm_call=_fake_llm,
    )
    assert report.kind == "llm_debate"
    assert report.verdict == "Buy"
    assert any(r.role == "bull" and "momentum" in r.thesis for r in report.rounds)


def test_llm_fallback_deterministic_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_LLM_DEBATE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STOCK_PLATFORM_LLM_API_KEY", raising=False)
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "deterministic")
    closes = [100 + i for i in range(20)]
    report = run_debate(
        _SeqProvider(closes),
        "600519",
        asof=date(2026, 2, 20),
        engine="llm",
    )
    assert report.kind == "debate"
    assert any("LLM fallback" in w for w in report.warnings)


def test_llm_fail_closed_when_fallback_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_LLM_DEBATE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STOCK_PLATFORM_LLM_API_KEY", raising=False)
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "fail-closed")
    closes = [100 + i for i in range(20)]
    with pytest.raises(LlmUnavailableError, match="fail-closed"):
        run_debate(
            _SeqProvider(closes),
            "600519",
            asof=date(2026, 2, 20),
            engine="llm",
        )


def test_llm_budget_exceeded_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_MAX_CALLS", "0")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "deterministic")
    closes = [100 + i for i in range(20)]
    report = run_debate(
        _SeqProvider(closes),
        "600519",
        asof=date(2026, 2, 20),
        engine="llm",
        llm_call=_fake_llm,
    )
    assert report.kind == "debate"
    assert any("budget" in w.lower() or "LlmBudgetExceeded" in w for w in report.warnings)


def test_llm_budget_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_MAX_CALLS", "0")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "fail-closed")
    closes = [100 + i for i in range(20)]
    with pytest.raises(LlmBudgetExceeded):
        run_debate(
            _SeqProvider(closes),
            "600519",
            asof=date(2026, 2, 20),
            engine="llm",
            llm_call=_fake_llm,
        )


def test_warn_if_truncated_provider_shapes() -> None:
    with pytest.warns(UserWarning, match="truncated"):
        assert warn_if_truncated({"stop_reason": "max_tokens"})
    with pytest.warns(UserWarning, match="truncated"):
        assert warn_if_truncated({"finish_reason": "length"})
    with pytest.warns(UserWarning, match="truncated"):
        assert warn_if_truncated({"finish_reason": "MAX_TOKENS"})
    with pytest.warns(UserWarning, match="truncated"):
        assert warn_if_truncated(
            {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            }
        )
    assert warn_if_truncated({"finish_reason": "stop"}) == []
    assert warn_if_truncated(None) == []


def test_debate_brief_picks_deterministic() -> None:
    closes = [100 + i for i in range(20)]
    brief = {
        "asof": "2026-02-20",
        "picks": [{"rank": 1, "symbol": "600519", "composite_score": 0.9}],
    }
    out = debate_brief_picks(_SeqProvider(closes), brief, engine="deterministic")
    assert out["engine"] == "deterministic"
    assert out["liveTradingEnabled"] is False
    assert out["debates"][0]["debate"]["kind"] == "debate"


def test_debate_brief_picks_llm_mock() -> None:
    closes = [100 + i for i in range(20)]
    brief = {
        "asof": "2026-02-20",
        "picks": [{"rank": 1, "symbol": "600519"}],
    }
    out = debate_brief_picks(
        _SeqProvider(closes), brief, engine="llm", llm_call=_fake_llm
    )
    assert out["engine"] == "llm"
    assert out["debates"][0]["debate"]["kind"] == "llm_debate"


def test_llm_status_default_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_LLM_DEBATE", raising=False)
    st = llm_debate_status()
    assert st["defaultEngine"] == "deterministic"
    assert st["ready"] is False
    assert st["fallback"] == "deterministic"
    assert st["maxCalls"] == 6
