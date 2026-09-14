"""Workbench-facing plugin wrappers."""

from __future__ import annotations

from datetime import date
from typing import Any

from .debate import DebateReport, build_debate_report
from .report import ResearchReport, SupportsMarketData, build_research_report, build_review_report


class ResearchAgentPlugin:
    """Stock research slot — data exclusively from injected MarketDataProvider."""

    slot = "stock-research"

    def __init__(self, provider: SupportsMarketData) -> None:
        self.provider = provider

    def run(self, symbol: str, *, asof: str | date | None = None) -> dict[str, Any]:
        report: ResearchReport = build_research_report(self.provider, symbol, asof=asof)
        return report.to_dict()


class ReviewAgentPlugin:
    """Post-market / review slot."""

    slot = "stock-review"

    def __init__(self, provider: SupportsMarketData) -> None:
        self.provider = provider

    def run(self, symbol: str, *, asof: str | date | None = None) -> dict[str, Any]:
        report = build_review_report(self.provider, symbol, asof=asof)
        return report.to_dict()


class DebateAgentPlugin:
    """Bull/Bear/Risk deterministic debate slot — no LLM."""

    slot = "stock-debate"

    def __init__(self, provider: SupportsMarketData) -> None:
        self.provider = provider

    def run(self, symbol: str, *, asof: str | date | None = None) -> dict[str, Any]:
        report: DebateReport = build_debate_report(self.provider, symbol, asof=asof)
        return report.to_dict()
