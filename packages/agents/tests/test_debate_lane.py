"""Debate lane tests — advisory sidecar contract (S5); no network / no key."""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

import pytest

from stock_platform_agents import (
    DEBATE_LANE_ENGINES,
    AgentError,
    LlmBudget,
    attach_debate_lane,
    debate_lane_summary,
    normalize_lane_engine,
)


class _SeqProvider:
    name = "seq"

    def __init__(self, closes: list[float], *, start: date = date(2026, 1, 2)) -> None:
        self._closes = closes
        self._start = start

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
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

    def get_realtime(self, symbols, *, asset_type="stock"):
        raise RuntimeError("no realtime")


def _fake_llm(system: str, user: str) -> str:
    return (
        '{"bull":"momentum","bear":"drawdown","risk":"vol",'
        '"verdict":"Buy","judge":"mock buy"}'
    )


def _brief() -> dict[str, Any]:
    return {
        "asof": "2026-02-20",
        "picks": [{"rank": 1, "symbol": "600519", "composite_score": 0.9}],
    }


def test_engines_and_normalize() -> None:
    assert DEBATE_LANE_ENGINES == ("off", "deterministic", "llm")
    assert normalize_lane_engine(None) == "off"
    assert normalize_lane_engine("") == "off"
    assert normalize_lane_engine("OFF") == "off"
    assert normalize_lane_engine("rules") == "deterministic"
    assert normalize_lane_engine("openai") == "llm"


def test_unknown_engine_raises() -> None:
    with pytest.raises(AgentError, match="unknown debate lane engine"):
        normalize_lane_engine("bogus")


def test_off_is_a_readonly_noop() -> None:
    provider = _SeqProvider([100 + i for i in range(20)])
    brief = _brief()
    before = copy.deepcopy(brief)
    lane = attach_debate_lane(provider, brief, engine="off")
    assert lane["enabled"] is False
    assert lane["engine"] == "off"
    assert lane["debateCount"] == 0
    assert lane["debates"] == []
    assert lane["advisory"] is True
    assert lane["excludedFromPerformance"] is True
    assert lane["budget"]["maxCalls"] >= 0
    assert brief == before  # lane is read-only
    assert "debates" not in brief  # never injected into the brief


def test_deterministic_lane_readonly_and_separated() -> None:
    provider = _SeqProvider([100 + i for i in range(20)])
    brief = _brief()
    before = copy.deepcopy(brief)
    lane = attach_debate_lane(provider, brief, engine="deterministic")
    assert lane["enabled"] is True
    assert lane["engine"] == "deterministic"
    assert lane["degraded"] is False
    assert lane["debateCount"] == 1
    item = lane["debates"][0]
    assert item["debate"]["kind"] == "debate"
    assert item["debate"]["verdict"] in {"Buy", "Hold", "Sell"}
    # 误判不进绩效 (M-A2): a verdict is not a rating and never lands on the brief.
    assert "rating" not in item
    assert "rating" not in item["debate"]
    assert brief == before
    assert "debates" not in brief
    # The lane never re-ranks / filters: the pick keeps its original score.
    assert brief["picks"][0]["composite_score"] == 0.9


def test_max_picks_caps_the_lane() -> None:
    provider = _SeqProvider([100 + i for i in range(20)])
    brief = {
        "asof": "2026-02-20",
        "picks": [
            {"rank": 1, "symbol": "600519"},
            {"rank": 2, "symbol": "000001"},
        ],
    }
    assert attach_debate_lane(provider, brief, engine="deterministic")["debateCount"] == 2
    capped = attach_debate_lane(provider, brief, engine="deterministic", max_picks=1)
    assert capped["debateCount"] == 1


def test_llm_lane_with_mock_is_not_degraded() -> None:
    provider = _SeqProvider([100 + i for i in range(20)])
    lane = attach_debate_lane(provider, _brief(), engine="llm", llm_call=_fake_llm)
    assert lane["engine"] == "llm"
    assert lane["degraded"] is False
    assert lane["debates"][0]["debate"]["kind"] == "llm_debate"
    assert lane["debates"][0]["debate"]["verdict"] == "Buy"


def test_explicit_budget_zero_degrades_to_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "deterministic")
    provider = _SeqProvider([100 + i for i in range(20)])
    lane = attach_debate_lane(
        provider,
        _brief(),
        engine="llm",
        llm_call=_fake_llm,
        budget=LlmBudget(max_calls=0),
    )
    assert lane["degraded"] is True
    assert lane["engine"] == "deterministic"
    assert lane["budget"]["maxCalls"] == 0
    assert lane["budget"]["callsUsed"] == 0
    assert lane["debates"][0]["debate"]["kind"] == "debate"


def test_explicit_budget_is_reported() -> None:
    provider = _SeqProvider([100 + i for i in range(20)])
    lane = attach_debate_lane(
        provider,
        _brief(),
        engine="llm",
        llm_call=_fake_llm,
        budget=LlmBudget(max_calls=3, max_tokens_soft=1000),
    )
    assert lane["budget"]["maxCalls"] == 3
    assert lane["budget"]["maxTokensSoft"] == 1000
    assert lane["budget"]["callsUsed"] == 1
    assert lane["budget"]["tokensEst"] > 0


def test_per_pick_failure_is_captured_not_raised() -> None:
    class _Empty:
        name = "empty"

        def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
            return []

        def get_realtime(self, symbols, *, asset_type="stock"):
            return []

    lane = attach_debate_lane(_Empty(), _brief(), engine="deterministic")
    assert lane["debateCount"] == 0
    assert lane["warnings"]
    assert "600519" in lane["warnings"][0]


def test_lane_summary_trims_round_text() -> None:
    provider = _SeqProvider([100 + i for i in range(20)])
    lane = attach_debate_lane(provider, _brief(), engine="deterministic")
    summary = debate_lane_summary(lane)
    assert summary["debateCount"] == 1
    assert "debates" not in summary
    assert summary["verdicts"][0]["symbol"] == "600519"
    assert summary["verdicts"][0]["kind"] == "debate"
    assert summary["excludedFromPerformance"] is True
