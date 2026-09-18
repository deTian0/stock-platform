"""Optional A-share analyst role prompt fragments (M-A3).

Prompts declare required provider capabilities; missing caps → fail-closed.
No URLs / no embedded HTTP (ADR 0009).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .errors import AgentError

ROLE_KEYS = ("policy", "hot_money", "unlock", "market", "news", "fundamentals")


@dataclass(frozen=True)
class RolePrompt:
    role: str
    title_zh: str
    required_capabilities: tuple[str, ...]
    system_prompt_zh: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "title_zh": self.title_zh,
            "required_capabilities": list(self.required_capabilities),
            "system_prompt_zh": self.system_prompt_zh,
        }


_ROLE_PROMPTS: dict[str, RolePrompt] = {
    "policy": RolePrompt(
        role="policy",
        title_zh="政策分析",
        required_capabilities=("news",),
        system_prompt_zh=(
            "你是 A 股政策分析角色。只依据已注入的新闻/公告要点，"
            "按政策层级、力度、生效时间窗整理影响；禁止编造未提供的条文；"
            "禁止把舆情当实时成交。无数据时明确标注缺失。"
        ),
    ),
    "hot_money": RolePrompt(
        role="hot_money",
        title_zh="游资追踪",
        required_capabilities=("fund_flow", "lhb", "concept_blocks"),
        system_prompt_zh=(
            "你是游资/短线资金追踪角色。结合资金流、龙虎榜与概念归属，"
            "描述量价异动与板块轮动框架；金额单位以元为准；"
            "不得引用未声明能力的席位或热股接口。"
        ),
    ),
    "unlock": RolePrompt(
        role="unlock",
        title_zh="解禁监控",
        required_capabilities=("unlock", "news"),
        system_prompt_zh=(
            "你是限售解禁监控角色。核对解禁类型、规模（万股）、时间与减持约束叙述；"
            "区分历史已解禁与未来待解禁；缺 unlock 数据时不得臆测。"
        ),
    ),
    "market": RolePrompt(
        role="market",
        title_zh="市场技术",
        required_capabilities=("daily",),
        system_prompt_zh=(
            "你是市场/技术分析角色。遵守 A 股涨跌停与 T+1 语境；"
            "仅使用已注入日 K/指标；指标名白名单宜短；禁止未来函数。"
        ),
    ),
    "news": RolePrompt(
        role="news",
        title_zh="新闻事件",
        required_capabilities=("news",),
        system_prompt_zh=(
            "你是新闻事件角色。按事件时间窗归纳；缺新闻标缺失；"
            "轻量特征非 LLM 摘要源文。"
        ),
    ),
    "fundamentals": RolePrompt(
        role="fundamentals",
        title_zh="基本面",
        required_capabilities=("financial",),
        system_prompt_zh=(
            "你是基本面角色。三表/估值仅用已注入 financial（或明确标注的离线 PIT）；"
            "历史复盘日不得把实时估值当当日事实。"
        ),
    ),
}


def list_role_prompts() -> list[dict[str, Any]]:
    return [ _ROLE_PROMPTS[k].as_dict() for k in ROLE_KEYS if k in _ROLE_PROMPTS ]


def get_role_prompt(role: str) -> RolePrompt:
    key = str(role or "").strip().lower()
    if key not in _ROLE_PROMPTS:
        raise AgentError(f"unknown role '{role}'; allowed={list(_ROLE_PROMPTS)}")
    return _ROLE_PROMPTS[key]


def assert_role_capabilities(
    role: str,
    available: Iterable[str],
) -> RolePrompt:
    """Fail-closed if any required capability is missing from ``available``."""
    prompt = get_role_prompt(role)
    have = {str(x).strip() for x in available if str(x).strip()}
    missing = [c for c in prompt.required_capabilities if c not in have]
    if missing:
        raise AgentError(
            f"role '{prompt.role}' missing capabilities: {', '.join(missing)}"
        )
    return prompt
