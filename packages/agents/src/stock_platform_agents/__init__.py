"""Thin agent plugins  - data only via stock_platform_providers."""

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
from .rating import RATINGS_5_TIER, parse_rating, to_ternary_verdict
from .report import ResearchReport, build_research_report, build_review_report
from .role_prompts import (
    ROLE_KEYS,
    RolePrompt,
    assert_role_capabilities,
    get_role_prompt,
    list_role_prompts,
)

__all__ = [
    "AgentError",
    "DebateAgentPlugin",
    "DebateReport",
    "LlmBudgetExceeded",
    "LlmUnavailableError",
    "RATINGS_5_TIER",
    "ROLE_KEYS",
    "ResearchAgentPlugin",
    "ResearchReport",
    "ReviewAgentPlugin",
    "RolePrompt",
    "assert_role_capabilities",
    "build_debate_report",
    "build_research_report",
    "build_review_report",
    "debate_brief_picks",
    "get_role_prompt",
    "list_role_prompts",
    "llm_debate_status",
    "parse_rating",
    "run_debate",
    "to_ternary_verdict",
    "warn_if_truncated",
]
__version__ = "3.11.1"
