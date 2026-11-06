"""Thin agent plugins — data only via stock_platform_providers.

Deterministic surface is imported eagerly. Optional LLM symbols are resolved via
``__getattr__`` (ADR 0088) so ``import stock_platform_agents`` does not load the
LLM module face. Prefer ``stock_platform_agents.llm`` for explicit LLM callers.
"""

from __future__ import annotations

from typing import Any

from .debate import DebateReport, build_debate_report
from .debate_lane import (
    DEBATE_LANE_ENGINES,
    attach_debate_lane,
    debate_lane_summary,
    normalize_lane_engine,
)
from .errors import AgentError
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
    "DEBATE_LANE_ENGINES",
    "DebateAgentPlugin",
    "DebateReport",
    "LlmBudget",
    "LlmBudgetExceeded",
    "LlmUnavailableError",
    "RATINGS_5_TIER",
    "ROLE_KEYS",
    "ResearchAgentPlugin",
    "ResearchReport",
    "ReviewAgentPlugin",
    "RolePrompt",
    "assert_role_capabilities",
    "attach_debate_lane",
    "build_debate_report",
    "build_research_report",
    "build_review_report",
    "debate_brief_picks",
    "debate_lane_summary",
    "deep_llm_graph_enabled",
    "deep_llm_graph_status",
    "get_role_prompt",
    "list_role_prompts",
    "llm_debate_status",
    "normalize_lane_engine",
    "parse_rating",
    "run_debate",
    "run_deep_llm_graph",
    "to_ternary_verdict",
    "warn_if_truncated",
]
__version__ = "4.14.0"

# LLM-only names: resolved lazily so deterministic importers stay LLM-free.
_LLM_EXPORTS = frozenset(
    {
        "LlmBudget",
        "LlmBudgetExceeded",
        "LlmUnavailableError",
        "debate_brief_picks",
        "deep_llm_graph_enabled",
        "deep_llm_graph_status",
        "llm_debate_status",
        "run_debate",
        "run_deep_llm_graph",
        "warn_if_truncated",
    }
)


def __getattr__(name: str) -> Any:
    if name not in _LLM_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import llm as _llm

    return getattr(_llm, name)


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
