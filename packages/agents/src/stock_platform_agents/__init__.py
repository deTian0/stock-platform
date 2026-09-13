"""Thin agent plugins — data only via stock_platform_providers."""

from .errors import AgentError
from .plugin import ResearchAgentPlugin, ReviewAgentPlugin
from .report import ResearchReport, build_research_report, build_review_report

__all__ = [
    "AgentError",
    "ResearchAgentPlugin",
    "ResearchReport",
    "ReviewAgentPlugin",
    "build_research_report",
    "build_review_report",
]

__version__ = "0.5.3"
