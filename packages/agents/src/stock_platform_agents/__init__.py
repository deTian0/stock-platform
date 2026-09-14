"""Thin agent plugins — data only via stock_platform_providers."""

from .debate import DebateReport, build_debate_report
from .errors import AgentError
from .plugin import DebateAgentPlugin, ResearchAgentPlugin, ReviewAgentPlugin
from .report import ResearchReport, build_research_report, build_review_report

__all__ = [
    "AgentError",
    "DebateAgentPlugin",
    "DebateReport",
    "ResearchAgentPlugin",
    "ResearchReport",
    "ReviewAgentPlugin",
    "build_debate_report",
    "build_research_report",
    "build_review_report",
]

__version__ = "1.13.2"
