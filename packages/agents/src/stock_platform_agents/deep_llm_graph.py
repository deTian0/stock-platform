"""Optional deeper multi-role LLM graph (M-A4) — non-default, fail-closed.

Uses ``role_prompts`` + injected provider facts only. **No dataflows / no URLs.**
Enable with ``STOCK_PLATFORM_DEEP_LLM_GRAPH=1`` plus existing LLM opt-in/key.
Default product path remains deterministic Bull/Bear/Risk (ADR 0017 / 0034).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from stock_platform_providers import normalize_symbol

from .errors import AgentError
from .llm_debate import (
    LlmBudgetExceeded,
    LlmCall,
    LlmUnavailableError,
    _LlmBudget,
    _default_openai_call,
    _llm_fallback_mode,
    _normalize_verdict,
    _require_llm_env,
    llm_debate_status,
    warn_if_truncated,
)
from .rating import parse_rating
from .report import SupportsMarketData, _historical_warning, _parse_asof
from .role_prompts import ROLE_KEYS, assert_role_capabilities

ENV_DEEP_LLM_GRAPH = "STOCK_PLATFORM_DEEP_LLM_GRAPH"

# Specialist roles first, then market/news/fundamentals, then judge via debate roles.
DEFAULT_GRAPH_ROLES: tuple[str, ...] = (
    "policy",
    "hot_money",
    "unlock",
    "market",
    "news",
    "fundamentals",
)


def deep_llm_graph_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return (source.get(ENV_DEEP_LLM_GRAPH) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def deep_llm_graph_status(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    llm = llm_debate_status()
    enabled = deep_llm_graph_enabled(env=source)
    ready = bool(enabled and llm.get("ready"))
    reasons: list[str] = []
    if not enabled:
        reasons.append(f"set {ENV_DEEP_LLM_GRAPH}=1 to opt in (default off)")
    reasons.extend(llm.get("reasons") or [])
    return {
        "enabled": enabled,
        "ready": ready,
        "defaultEngine": "deterministic",
        "envVar": ENV_DEEP_LLM_GRAPH,
        "roles": list(DEFAULT_GRAPH_ROLES),
        "llm": llm,
        "reasons": reasons,
        "note": (
            "可选更深多角色 LLM 图（M-A4）；非默认；缺密钥/依赖 fail-closed；"
            "数据仅经注入 Provider；禁止 dataflows。"
        ),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


def _require_deep_env(*, llm_call: LlmCall | None, env: Mapping[str, str] | None) -> None:
    if not deep_llm_graph_enabled(env=env):
        raise LlmUnavailableError(
            f"deep LLM graph disabled (fail-closed); set {ENV_DEEP_LLM_GRAPH}=1"
        )
    _require_llm_env(llm_call=llm_call)


def _facts_blob(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof_d: date,
    lookback_days: int,
) -> tuple[str, list[str], int, float | None]:
    warnings: list[str] = []
    hist = _historical_warning(asof_d)
    if hist:
        warnings.append(hist)
    start = date.fromordinal(max(asof_d.toordinal() - int(lookback_days), 1))
    bars = provider.get_daily([symbol], start=start, end=asof_d) or []
    bars = [b for b in bars if str(b.get("date", ""))[:10] <= asof_d.isoformat()]
    if not bars:
        raise AgentError(f"no daily bars for {symbol} asof {asof_d.isoformat()}")
    closes = []
    for b in bars:
        try:
            closes.append(float(b.get("close")))
        except (TypeError, ValueError):
            continue
    last_close = closes[-1] if closes else None
    first = closes[0] if closes else None
    ret = ((last_close / first) - 1.0) if first and last_close else 0.0
    if asof_d == date.today():
        try:
            provider.get_realtime([symbol])
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"realtime unavailable: {exc}")
    else:
        warnings.append("已跳过 realtime（历史分析日）")
    facts = (
        f"symbol={symbol} asof={asof_d.isoformat()} daily_bars={len(bars)} "
        f"last_close={last_close} window_return={ret:.4f}\n"
        f"recent_closes={closes[-10:]}"
    )
    return facts, warnings, len(bars), last_close


def _parse_role_payload(text: str) -> dict[str, Any]:
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"summary": raw[:2000], "rating": "Hold"}


def run_deep_llm_graph(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
    lookback_days: int = 60,
    available_capabilities: Iterable[str] | None = None,
    roles: Sequence[str] | None = None,
    llm_call: LlmCall | None = None,
    budget: _LlmBudget | None = None,
    env: Mapping[str, str] | None = None,
    response_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run optional multi-role LLM graph; data only from ``provider``.

    Missing graph env / LLM key / caps → fail-closed (``LlmUnavailableError`` /
    ``AgentError``). Never silently falls back to inventing specialist text unless
    ``STOCK_PLATFORM_LLM_FALLBACK=deterministic`` (then returns a thin stub with
    warnings — still not the default daily path).
    """
    try:
        _require_deep_env(llm_call=llm_call, env=env)
    except LlmUnavailableError as exc:
        mode = _llm_fallback_mode()
        if mode in {"deterministic", "rules", "m12", "1", "true", "yes", "on"}:
            return {
                "ok": False,
                "kind": "deep_llm_graph_fallback",
                "symbol": normalize_symbol(symbol),
                "asof": str(asof or "")[:10] or None,
                "engine": "deterministic_fallback",
                "warnings": [f"deep graph unavailable → fallback ({exc})"],
                "roles": [],
                "verdict": "Hold",
                "environment": "SIMULATE",
                "liveTradingEnabled": False,
                "disclaimer": "模板结论，非投资建议；更深图未启用/失败。",
            }
        raise

    call = llm_call or _default_openai_call
    session = budget or _LlmBudget()
    code = normalize_symbol(symbol)
    asof_d = _parse_asof(asof)
    caps = list(available_capabilities) if available_capabilities is not None else ["daily"]
    role_keys = list(roles) if roles else list(DEFAULT_GRAPH_ROLES)

    facts, warnings_list, n_bars, last_close = _facts_blob(
        provider, code, asof_d=asof_d, lookback_days=lookback_days
    )

    role_outputs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        for role in role_keys:
            if role not in ROLE_KEYS:
                raise AgentError(f"unknown deep-graph role '{role}'")
            try:
                prompt = assert_role_capabilities(role, caps)
            except AgentError as miss:
                skipped.append({"role": role, "reason": str(miss)})
                warnings_list.append(f"skipped role '{role}': {miss}")
                continue
            system = (
                prompt.system_prompt_zh
                + " 仅依据用户提供的 facts；用 JSON 回复："
                '{"summary":"...","rating":"Buy|Overweight|Hold|Underweight|Sell"}。'
                "禁止编造未提供的价格或公告；非投资建议。"
            )
            user = f"role={role}\n{facts}"
            session.before_call(system, user)
            content = call(system, user)
            session.after_call(system, user, content)
            trunc = warn_if_truncated(response_meta)
            warnings_list.extend(trunc)
            payload = _parse_role_payload(content)
            rating = parse_rating(str(payload.get("rating") or "Hold"), default="Hold")
            role_outputs.append(
                {
                    "role": role,
                    "title_zh": prompt.title_zh,
                    "summary": str(payload.get("summary") or "")[:2000],
                    "rating": rating,
                    "required_capabilities": list(prompt.required_capabilities),
                }
            )
        if not role_outputs:
            raise AgentError(
                "deep LLM graph fail-closed: no roles runnable "
                f"(skipped={skipped})"
            )

        # Judge aggregates specialist ratings (no extra data source).
        ratings = [r["rating"] for r in role_outputs]
        buyish = sum(1 for r in ratings if r in {"Buy", "Overweight"})
        sellish = sum(1 for r in ratings if r in {"Sell", "Underweight"})
        if buyish > sellish and buyish >= 2:
            verdict = "Buy"
        elif sellish > buyish and sellish >= 2:
            verdict = "Sell"
        else:
            verdict = "Hold"
        judge_system = (
            "You are the portfolio judge for A-share paper research. "
            'Reply JSON only: {"verdict":"Buy|Hold|Sell","judge":"..."}. '
            "Use only the specialist summaries; not investment advice."
        )
        judge_user = json.dumps(
            {"symbol": code, "asof": asof_d.isoformat(), "roles": role_outputs},
            ensure_ascii=False,
        )
        session.before_call(judge_system, judge_user)
        judge_raw = call(judge_system, judge_user)
        session.after_call(judge_system, judge_user, judge_raw)
        judge_payload = _parse_role_payload(judge_raw)
        if judge_payload.get("verdict") or judge_payload.get("rating"):
            verdict = _normalize_verdict(
                judge_payload.get("verdict") or judge_payload.get("rating")
            )
        judge_text = str(
            judge_payload.get("judge")
            or judge_payload.get("summary")
            or f"aggregated verdict {verdict}"
        )[:2000]
    except (LlmUnavailableError, LlmBudgetExceeded, AgentError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise LlmUnavailableError(f"deep LLM graph failed (fail-closed): {exc}") from exc

    return {
        "ok": True,
        "kind": "deep_llm_graph",
        "symbol": code,
        "asof": asof_d.isoformat(),
        "provider": getattr(provider, "name", type(provider).__name__),
        "engine": "llm_deep_graph",
        "roles": role_outputs,
        "skippedRoles": skipped,
        "verdict": verdict,
        "judge": judge_text,
        "daily_bars": n_bars,
        "last_close": last_close,
        "warnings": warnings_list,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": (
            "可选更深多角色 LLM 图（M-A4）；非默认日用路径；"
            "数据仅经 MarketDataProvider；非投资建议。"
        ),
    }
