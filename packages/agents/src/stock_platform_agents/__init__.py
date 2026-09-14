"""Thin agent plugins — data only via stock_platform_providers."""

from .debate import DebateReport, build_debate_report
from .errors import AgentError
from .llm_debate import (
    LlmBudgetExceeded,
    LlmUnavailableError,
    debate_brief_picks,
    llm_debate_status,
    run_debate,
    warn_if_truncated,
)
from .plugin import DebateAgentPlugin, ResearchAgentPlugin, ReviewAgentPlugin
from .report import ResearchReport, build_research_report, build_review_report

__all__ = [
    "AgentError",
    "DebateAgentPlugin",
    "DebateReport",
    "LlmBudgetExceeded",
    "LlmUnavailableError",
    "ResearchAgentPlugin",
    "ResearchReport",
    "ReviewAgentPlugin",
    "build_debate_report",
    "build_research_report",
    "build_review_report",
    "debate_brief_picks",
    "llm_debate_status",
    "run_debate",
    "warn_if_truncated",
]
__version__ = "3.8.0"
