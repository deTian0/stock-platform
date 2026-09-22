"""M-A4 deep LLM graph — default off, fail-closed, zero public net."""

from __future__ import annotations

from datetime import date

import pytest

from stock_platform_agents.deep_llm_graph import (
    deep_llm_graph_enabled,
    deep_llm_graph_status,
    run_deep_llm_graph,
)
from stock_platform_agents.errors import AgentError
from stock_platform_agents.llm_debate import LlmUnavailableError


class _FakeProvider:
    name = "replay"

    def get_daily(self, symbols, *, start, end):
        rows = []
        for i in range(10):
            d = date(2026, 9, 1 + i)
            if d > end:
                break
            rows.append({"date": d.isoformat(), "symbol": symbols[0], "close": 10.0 + i * 0.1})
        return rows

    def get_realtime(self, symbols):
        return []


def test_deep_graph_default_off() -> None:
    assert deep_llm_graph_enabled(env={}) is False
    st = deep_llm_graph_status(env={})
    assert st["enabled"] is False
    assert st["ready"] is False


def test_deep_graph_fail_closed_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_LLM_FALLBACK", "fail-closed")
    monkeypatch.delenv("STOCK_PLATFORM_DEEP_LLM_GRAPH", raising=False)
    with pytest.raises(LlmUnavailableError, match="deep LLM graph disabled"):
        run_deep_llm_graph(
            _FakeProvider(),
            "600519",
            asof="2026-09-02",
            available_capabilities=["daily"],
            roles=["market"],
            llm_call=lambda s, u: '{"summary":"x","rating":"Hold"}',
            env={},
        )


def test_deep_graph_mock_llm_market_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_DEEP_LLM_GRAPH", "1")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_DEBATE", "1")
    monkeypatch.setenv("STOCK_PLATFORM_LLM_API_KEY", "test-key-not-real")
    calls: list[str] = []

    def _call(system: str, user: str) -> str:
        calls.append(user[:40])
        if "portfolio judge" in system.lower() or "judge" in system.lower():
            return '{"verdict":"Hold","judge":"neutral"}'
        return '{"summary":"ok","rating":"Hold"}'

    out = run_deep_llm_graph(
        _FakeProvider(),
        "600519",
        asof="2026-09-02",
        available_capabilities=["daily"],
        roles=["market"],
        llm_call=_call,
        env={
            "STOCK_PLATFORM_DEEP_LLM_GRAPH": "1",
            "STOCK_PLATFORM_LLM_DEBATE": "1",
            "STOCK_PLATFORM_LLM_API_KEY": "test-key-not-real",
        },
    )
    assert out["ok"] is True
    assert out["kind"] == "deep_llm_graph"
    assert out["liveTradingEnabled"] is False
    assert len(out["roles"]) == 1
    assert out["roles"][0]["role"] == "market"
    assert len(calls) >= 2


def test_deep_graph_skips_missing_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCK_PLATFORM_DEEP_LLM_GRAPH", "1")
    out = run_deep_llm_graph(
        _FakeProvider(),
        "600519",
        asof="2026-09-02",
        available_capabilities=["daily"],
        roles=["hot_money", "market"],
        llm_call=lambda s, u: (
            '{"verdict":"Buy","judge":"j"}'
            if "judge" in s.lower()
            else '{"summary":"m","rating":"Buy"}'
        ),
        env={
            "STOCK_PLATFORM_DEEP_LLM_GRAPH": "1",
            "STOCK_PLATFORM_LLM_DEBATE": "1",
            "STOCK_PLATFORM_LLM_API_KEY": "k",
        },
    )
    assert out["ok"] is True
    roles = {r["role"] for r in out["roles"]}
    assert "market" in roles
    assert "hot_money" not in roles
    assert any(s["role"] == "hot_money" for s in out["skippedRoles"])
