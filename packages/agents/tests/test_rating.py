"""M-A2 rating boundary matrix — ported from TradingAgents-astock."""

from __future__ import annotations

import pytest

from stock_platform_agents.rating import (
    RATINGS_5_TIER,
    parse_rating,
    to_ternary_verdict,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("最终评级：Buy", "Buy"),
        ("最终评级：Sell", "Sell"),
        ("投资建议：Overweight", "Overweight"),
        ("评级 - buy", "Buy"),
        ("最终评级：**Sell**", "Sell"),
        ("最终评级：Buy。", "Buy"),
        ("最终评级：Sell，理由如下", "Sell"),
        ("最终评级：Buy：核心逻辑", "Buy"),
        ("最终评级：Buy（基于风险收益比）", "Buy"),
        ("最终评级：Underweight(估值偏高)", "Underweight"),
        ("最终评级：Hold【中性】", "Hold"),
        ("最终评级：Sell\n理由若干", "Sell"),
        ("最终评级：Buyer interest remains weak", "Hold"),
        ("建议：Selling pressure is high", "Hold"),
        ("建议：Sell-off risk remains elevated", "Hold"),
        ("最终评级：Buy-side interest is weak", "Hold"),
        ("最终评级：Buy2024", "Hold"),
        ("最终评级：Buy_target", "Hold"),
        ("建议：**Sell**-off risk remains elevated", "Hold"),
        ("最终评级：**Buy**-side interest is weak", "Hold"),
        ("最终评级：**Buy**2024", "Hold"),
        ("最终评级：**Sell**- 退出", "Sell"),
        ("最终评级：Sell- 退出", "Sell"),
        ("最终评级：买入", "Buy"),
        ("最终评级：卖出", "Sell"),
        ("投资建议: **增持**", "Overweight"),
    ],
)
def test_rating_value_boundary_matrix(text: str, expected: str) -> None:
    assert parse_rating(text) == expected


def test_ratings_five_tier_order() -> None:
    assert RATINGS_5_TIER[0] == "Buy"
    assert RATINGS_5_TIER[-1] == "Sell"
    assert len(RATINGS_5_TIER) == 5


def test_to_ternary_verdict() -> None:
    assert to_ternary_verdict("Overweight") == "Buy"
    assert to_ternary_verdict("Underweight") == "Sell"
    assert to_ternary_verdict("Hold") == "Hold"
