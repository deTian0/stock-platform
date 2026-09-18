"""Shared 5-tier rating vocabulary + deterministic heuristic parser (M-A2).

Ported from TradingAgents-astock ``agents/utils/rating.py`` boundary rules.
**No HTTP / dataflows.** Debate UI may still ternary-map via ``to_ternary_verdict``.
"""

from __future__ import annotations

import re
from typing import Literal, Tuple

# Canonical, ordered 5-tier scale (most bullish → most bearish).
RATINGS_5_TIER: Tuple[str, ...] = (
    "Buy",
    "Overweight",
    "Hold",
    "Underweight",
    "Sell",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)

_CN_RATING_MAP = {
    "强烈买入": "Buy",
    "买入": "Buy",
    "买进": "Buy",
    "增持": "Overweight",
    "持有": "Hold",
    "中性": "Hold",
    "观望": "Hold",
    "维持": "Hold",
    "减持": "Underweight",
    "强烈卖出": "Sell",
    "清仓": "Sell",
    "卖出": "Sell",
}
_CN_ALT = "|".join(sorted(_CN_RATING_MAP, key=len, reverse=True))

_CN_LABEL_PREFIX = (
    r"(?:最终评级|评级|投资评级|评级结论|最终投资建议|投资建议|操作建议|"
    r"推荐评级|建议|推荐)\s*[:：\-]\s*\*{0,2}\s*"
)

_CN_LABEL_RE = re.compile(_CN_LABEL_PREFIX + r"(" + _CN_ALT + r")")

# 「不能延续成更长的词」— do not enumerate punctuation allow-lists.
_WORD_CONTINUATION = r"(?:[A-Za-z0-9_]|-(?=[A-Za-z0-9_]))"
_RATING_VALUE_END = r"(?!\*{0,2}" + _WORD_CONTINUATION + r")"

_CN_LABEL_EN_RE = re.compile(
    _CN_LABEL_PREFIX + r"(" + "|".join(RATINGS_5_TIER) + r")" + _RATING_VALUE_END,
    re.IGNORECASE,
)
_CN_TERM_RE = re.compile(_CN_ALT)

TernaryVerdict = Literal["Buy", "Hold", "Sell"]


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from English or Chinese prose."""
    # 1. English explicit label
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    # 2. Chinese explicit label
    m = _CN_LABEL_RE.search(text)
    if m:
        return _CN_RATING_MAP[m.group(1)]

    # 2b. Chinese label + English rating word
    m = _CN_LABEL_EN_RE.search(text)
    if m:
        return m.group(1).capitalize()

    # 3. Bare English rating word
    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in _RATING_SET:
                return clean.capitalize()

    # 4. Bare Chinese rating term
    m = _CN_TERM_RE.search(text)
    if m:
        return _CN_RATING_MAP[m.group(0)]

    return default


def to_ternary_verdict(rating: str) -> TernaryVerdict:
    """Map 5-tier → Buy|Hold|Sell for deterministic / LLM debate slots."""
    r = str(rating or "Hold").strip().capitalize()
    if r in {"Buy", "Overweight"}:
        return "Buy"
    if r in {"Sell", "Underweight"}:
        return "Sell"
    return "Hold"
