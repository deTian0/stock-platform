"""Optional LLM advisory surface (sidecar).

Deterministic product path does **not** import this package. Opt in via::

    pip install 'stock-platform-agents[llm]'
    STOCK_PLATFORM_LLM_DEBATE=1
    STOCK_PLATFORM_LLM_PROVIDER=deepseek   # default is workbuddy (no in-process LLM)
    DEEPSEEK_API_KEY=...
    DEEPSEEK_BASE_URL=https://api.deepseek.com
    DEEPSEEK_MODEL=deepseek-chat

Also: ``STOCK_PLATFORM_DEEP_LLM_GRAPH=1`` for the deeper multi-role graph (M-A4).

Physical modules remain ``llm_debate`` / ``deep_llm_graph`` / ``llm_provider`` for
back-compat; this package is the **canonical import face** for LLM callers.
"""

from __future__ import annotations

from stock_platform_agents.deep_llm_graph import (
    DEFAULT_GRAPH_ROLES,
    ENV_DEEP_LLM_GRAPH,
    deep_llm_graph_enabled,
    deep_llm_graph_status,
    run_deep_llm_graph,
)
from stock_platform_agents.llm_debate import (
    LlmBudget,
    LlmBudgetExceeded,
    LlmCall,
    LlmUnavailableError,
    build_llm_debate_report,
    debate_brief_picks,
    llm_debate_status,
    run_debate,
    warn_if_truncated,
)
from stock_platform_agents.llm_provider import (
    ENV_LLM_PROVIDER,
    LlmProviderConfig,
    LlmProviderError,
    chat_completion,
    chat_text,
    llm_provider_status,
    resolve_llm_provider,
)

__all__ = [
    "DEFAULT_GRAPH_ROLES",
    "ENV_DEEP_LLM_GRAPH",
    "ENV_LLM_PROVIDER",
    "LlmBudget",
    "LlmBudgetExceeded",
    "LlmCall",
    "LlmProviderConfig",
    "LlmProviderError",
    "LlmUnavailableError",
    "build_llm_debate_report",
    "chat_completion",
    "chat_text",
    "debate_brief_picks",
    "deep_llm_graph_enabled",
    "deep_llm_graph_status",
    "llm_debate_status",
    "llm_provider_status",
    "resolve_llm_provider",
    "run_debate",
    "run_deep_llm_graph",
    "warn_if_truncated",
]
