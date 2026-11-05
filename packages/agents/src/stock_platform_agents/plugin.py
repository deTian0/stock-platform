"""Workbench-facing plugin wrappers."""

from __future__ import annotations

from datetime import date
from typing import Any

from .debate import DebateReport, build_debate_report
from .errors import AgentError
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
    """Bull/Bear/Risk debate slot — deterministic by default; optional LLM.

    ``engine=deterministic`` (default) never imports the LLM module face (ADR 0088).
    ``engine=llm`` lazy-loads ``llm_debate.run_debate``.
    """

    slot = "stock-debate"

    def __init__(self, provider: SupportsMarketData) -> None:
        self.provider = provider

    def run(
        self,
        symbol: str,
        *,
        asof: str | date | None = None,
        engine: str = "deterministic",
    ) -> dict[str, Any]:
        eng = (engine or "deterministic").strip().lower()
        if eng in {"", "deterministic", "rules", "m12"}:
            report: DebateReport = build_debate_report(
                self.provider, symbol, asof=asof
            )
            return report.to_dict()
        if eng in {"llm", "openai"}:
            from .llm_debate import run_debate

            report = run_debate(
                self.provider, symbol, asof=asof, engine="llm"
            )
            return report.to_dict()
        raise AgentError(f"unknown debate engine={engine!r}; use deterministic|llm")
