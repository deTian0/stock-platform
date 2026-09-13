"""Agent plugin tests — fixtures via ReplayProvider only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_platform_agents import (
    AgentError,
    ResearchAgentPlugin,
    ReviewAgentPlugin,
    build_research_report,
)
from stock_platform_providers import ReplayProvider, ReplayTransport, SymbolError

FIXTURES = Path(__file__).resolve().parents[2] / "providers" / "tests" / "fixtures"


@pytest.fixture()
def provider() -> ReplayProvider:
    return ReplayProvider(ReplayTransport(FIXTURES))


def test_research_uses_provider_not_http(provider: ReplayProvider) -> None:
    plugin = ResearchAgentPlugin(provider)
    out = plugin.run("SH600519", asof="2026-09-02")
    assert out["symbol"] == "600519"
    assert out["provider"] == "replay"
    assert out["kind"] == "research"
    assert out["daily_bars"] >= 1
    assert any("早于今天" in w or "跳过 realtime" in w for w in out["warnings"])


def test_historical_skips_realtime(provider: ReplayProvider) -> None:
    report = build_research_report(provider, "600519", asof=date(2026, 9, 1))
    assert any("跳过 realtime" in w for w in report.warnings)


def test_rejects_hk(provider: ReplayProvider) -> None:
    with pytest.raises(SymbolError):
        ResearchAgentPlugin(provider).run("00700")


def test_review_slot(provider: ReplayProvider) -> None:
    out = ReviewAgentPlugin(provider).run("600519", asof="2026-09-02")
    assert out["kind"] == "review"
    assert "verdict" in out["roles"]


def test_missing_bars_raises(provider: ReplayProvider) -> None:
    with pytest.raises(AgentError):
        build_research_report(provider, "600519", asof=date(2020, 1, 1))
