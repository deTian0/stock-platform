"""M-A3 role prompt capability gating tests."""

from __future__ import annotations

import pytest

from stock_platform_agents import AgentError
from stock_platform_agents.role_prompts import (
    assert_role_capabilities,
    get_role_prompt,
    list_role_prompts,
)


def test_list_role_prompts_includes_astock_specialists() -> None:
    roles = {r["role"] for r in list_role_prompts()}
    assert {"policy", "hot_money", "unlock"}.issubset(roles)


def test_hot_money_requires_concept_blocks() -> None:
    p = get_role_prompt("hot_money")
    assert "concept_blocks" in p.required_capabilities
    assert "http" not in p.system_prompt_zh.lower()
    assert "://" not in p.system_prompt_zh


def test_assert_role_capabilities_fail_closed() -> None:
    with pytest.raises(AgentError, match="missing capabilities"):
        assert_role_capabilities("unlock", available=["news"])


def test_assert_role_capabilities_ok() -> None:
    p = assert_role_capabilities("policy", available=["news", "daily"])
    assert p.role == "policy"
