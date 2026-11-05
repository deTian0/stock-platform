"""Structured-reason schema, vacuous-phrase detection and deterministic fallback.

Final Board reasons must carry four falsifiable fields (ADR 0093 §6, README
"LLM 理由约束"). This module is the single validator:

* :func:`validate_reason` — schema + 空话检测 (no network, no LLM).
* :func:`apply_reason_policy` — merge optional LLM reasons over the rule-filled
  ones; any LLM reason that fails validation falls back to the deterministic
  reason and is recorded as an observable degrade. LLM text never changes
  *which* names pass (that is Round2 Set A only).
* :func:`build_reason_prompt` — prompt template + JSON schema for the injected
  LLM sidecar (research stays agents-free).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence

REQUIRED_REASON_FIELDS: tuple[str, ...] = (
    "holdingPeriod",
    "trigger",
    "expectation",
    "invalidation",
)

# Minimum useful length per field (characters, after strip).
MIN_FIELD_CHARS: dict[str, int] = {
    "holdingPeriod": 3,
    "trigger": 6,
    "expectation": 8,
    "invalidation": 6,
}
MAX_FIELD_CHARS = 200

# Slogans that carry no checkable content. A field made only of these (after
# removing them, < 4 meaningful chars left) is vacuous.
BANNED_PHRASES: tuple[str, ...] = (
    "看好",
    "情绪好",
    "情绪向好",
    "前景广阔",
    "前景可期",
    "值得关注",
    "值得期待",
    "趋势向好",
    "有望上涨",
    "有望走高",
    "潜力巨大",
    "强烈推荐",
    "积极信号",
    "利好",
    "稳健增长",
    "低估",
    "龙头",
    "长期价值",
    "估值合理",
    "基本面良好",
    "表现优异",
    "走势强劲",
)

# A falsifiable expectation / invalidation must contain something measurable:
# a number, a comparator, or a concrete observable verb.
_MEASURABLE = re.compile(
    r"(\d|≥|≤|>|<|跌破|站上|突破|低于|高于|超过|不足|缺失|撤销|排名|分位|相对|净流入|成交额|涨停|跌停|回落|收盘)"
)
_HOLDING_NUMBER = re.compile(r"\d")

LLM_REASON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": list(REQUIRED_REASON_FIELDS),
    "additionalProperties": True,
    "properties": {
        "holdingPeriod": {
            "type": "string",
            "description": "持有期，必须含具体交易日数或区间，如「5–10 交易日」",
        },
        "trigger": {
            "type": "string",
            "description": "入场/关注触发条件，必须是可观察事实（价格、成交额、资金流、事件日期）",
        },
        "expectation": {
            "type": "string",
            "description": "可证伪预期：写明指标、方向、幅度或排名，如「5 日内相对沪深300 超额 ≥ 1%」",
        },
        "invalidation": {
            "type": "string",
            "description": "失效条件：出现什么可观察事实则论点作废，如「收盘跌破 MA20」",
        },
    },
}


def _strip_banned(text: str) -> str:
    out = text
    for phrase in BANNED_PHRASES:
        out = out.replace(phrase, "")
    return re.sub(r"[\s，。；、,.;:：！!？?\-—（）()]+", "", out)


def validate_reason(reason: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return ``{"ok": bool, "problems": [str, ...]}`` (never raises)."""
    problems: list[str] = []
    if not isinstance(reason, Mapping):
        return {"ok": False, "problems": ["理由不是对象"]}

    for key in REQUIRED_REASON_FIELDS:
        raw = reason.get(key)
        text = str(raw).strip() if raw is not None else ""
        if not text:
            problems.append(f"缺字段 {key}")
            continue
        if len(text) > MAX_FIELD_CHARS:
            problems.append(f"{key} 过长（>{MAX_FIELD_CHARS} 字）")
            continue
        if len(text) < MIN_FIELD_CHARS[key]:
            problems.append(f"{key} 过短（<{MIN_FIELD_CHARS[key]} 字）")
            continue
        if len(_strip_banned(text)) < 4:
            problems.append(f"{key} 为空话/口号")
            continue
        if key == "holdingPeriod" and not _HOLDING_NUMBER.search(text):
            problems.append("holdingPeriod 缺具体交易日数")
        if key in {"expectation", "invalidation"} and not _MEASURABLE.search(text):
            problems.append(f"{key} 不可证伪（缺数字/比较/可观察事实）")
    return {"ok": not problems, "problems": problems}


def build_reason_prompt(row: Mapping[str, Any]) -> dict[str, Any]:
    """Prompt + schema bundle for an injected LLM sidecar (no network here)."""
    facts = {
        k: row.get(k)
        for k in ("code", "name", "school", "schoolName", "score", "industry")
        if row.get(k) is not None
    }
    src = row.get("sourceFields")
    if isinstance(src, Mapping):
        facts["sourceFields"] = dict(src)
    system = (
        "你是 A 股研究助理，只为已通过硬闸的候选写结构化理由。"
        "只能引用 facts 中给出的数字，不得编造数据；不得判定是否入选。"
        "禁止空话与口号（如：看好、情绪好、前景广阔、值得关注、利好、龙头）。"
        "仅输出一个 JSON 对象，字段：holdingPeriod / trigger / expectation / invalidation；"
        "expectation 与 invalidation 必须含数字或可观察比较（跌破/站上/排名/净流入）。"
    )
    return {
        "system": system,
        "facts": facts,
        "schema": LLM_REASON_SCHEMA,
        "bannedPhrases": list(BANNED_PHRASES),
        "excludedFromPerformance": True,
    }


ReasonProvider = Callable[[Sequence[Mapping[str, Any]]], Mapping[str, Mapping[str, Any]]]


def apply_reason_policy(
    rows: Sequence[Mapping[str, Any]],
    *,
    reason_provider: ReasonProvider | Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Return ``(kept, dropped, stats)``.

    Rule-filled reasons are the baseline. An LLM reason (from ``reason_provider``
    keyed by code) replaces it only if :func:`validate_reason` passes; otherwise
    the deterministic reason is kept and ``reasonDegrade`` records why. A row
    whose *deterministic* reason is itself invalid is dropped (fail-closed).
    """
    llm_map: Mapping[str, Mapping[str, Any]] = {}
    provider_error: str | None = None
    if reason_provider is not None:
        try:
            raw = reason_provider(rows) if callable(reason_provider) else reason_provider
            llm_map = dict(raw or {})
        except Exception as exc:  # noqa: BLE001 — LLM sidecar is best-effort
            provider_error = f"{type(exc).__name__}"
            llm_map = {}

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    stats = {"llmAccepted": 0, "llmFallback": 0, "ruleDropped": 0}

    for row in rows:
        item = dict(row)
        base_check = validate_reason(item)
        code = str(item.get("code") or "")
        llm_reason = llm_map.get(code)

        if llm_reason is not None:
            check = validate_reason(llm_reason)
            if check["ok"]:
                for key in REQUIRED_REASON_FIELDS:
                    item[key] = str(llm_reason[key]).strip()
                item["reasonSource"] = "llm"
                stats["llmAccepted"] += 1
            else:
                item["reasonSource"] = "rule_fallback"
                item["reasonDegrade"] = "；".join(check["problems"])
                stats["llmFallback"] += 1
        elif reason_provider is not None:
            item["reasonSource"] = "rule_fallback"
            item["reasonDegrade"] = (
                f"LLM provider 错误：{provider_error}" if provider_error else "LLM 未给出该票理由"
            )
            stats["llmFallback"] += 1
        else:
            item["reasonSource"] = "rule"

        # Re-check the final row (rule baseline when LLM was rejected).
        final_check = validate_reason(item) if item["reasonSource"] == "llm" else base_check
        if not final_check["ok"]:
            item["degradeReason"] = "结构化理由不合格: " + "；".join(final_check["problems"])
            dropped.append(item)
            stats["ruleDropped"] += 1
            continue
        item["excludedFromPerformance"] = True
        kept.append(item)

    return kept, dropped, stats


__all__ = [
    "BANNED_PHRASES",
    "LLM_REASON_SCHEMA",
    "REQUIRED_REASON_FIELDS",
    "apply_reason_policy",
    "build_reason_prompt",
    "validate_reason",
]
