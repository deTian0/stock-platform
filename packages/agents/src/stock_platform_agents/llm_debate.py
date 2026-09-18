"""Optional LLM debate — soft-import / budget / truncation / fallback (ADR 0034 + 0044).

Default product path remains ``build_debate_report`` (deterministic, ADR 0017).
This module never embeds Eastmoney URLs; bars come only from the injected provider.

Cost / quality (ADR 0045):
- ``STOCK_PLATFORM_LLM_MAX_CALLS`` (default 6)
- ``STOCK_PLATFORM_LLM_MAX_TOKENS`` soft estimate (chars/4); unset = no soft cap
- ``warn_if_truncated`` covers Anthropic / OpenAI Chat / Gemini / Responses shapes
- On budget exceed or LLM failure: degrade to deterministic when
  ``STOCK_PLATFORM_LLM_FALLBACK=deterministic`` (default); else fail-closed
"""

from __future__ import annotations

import json
import os
import re
import warnings
from datetime import date
from typing import Any, Callable, Mapping

from stock_platform_providers import normalize_symbol

from .debate import DebateReport, DebateRound, Verdict, _closes, build_debate_report
from .errors import AgentError
from .report import SupportsMarketData, _historical_warning, _parse_asof

LlmCall = Callable[[str, str], str]


class LlmUnavailableError(AgentError):
    """Raised when optional LLM deps/keys are missing or the call fails closed."""


class LlmBudgetExceeded(LlmUnavailableError):
    """Raised when call/token budget is exhausted before or during LLM use."""


# Provider truncation markers (lowercase compare). Missing one shape = silent truncate.
_TRUNCATION_MARKERS = {
    "stop_reason": {"max_tokens"},
    "finish_reason": {"length", "max_tokens"},
}
_RESPONSES_INCOMPLETE_REASONS = {"max_output_tokens", "max_tokens"}


def llm_debate_status() -> dict[str, Any]:
    """Describe whether optional LLM debate can run (no network)."""
    enabled = os.environ.get("STOCK_PLATFORM_LLM_DEBATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    key = (
        os.environ.get("STOCK_PLATFORM_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    openai_ok = False
    openai_err: str | None = None
    try:
        import openai  # noqa: F401

        openai_ok = True
    except Exception as exc:  # noqa: BLE001
        openai_err = f"{type(exc).__name__}: {exc}"
    ready = bool(enabled and key and openai_ok)
    reasons: list[str] = []
    if not enabled:
        reasons.append("set STOCK_PLATFORM_LLM_DEBATE=1 to opt in")
    if not key:
        reasons.append("missing STOCK_PLATFORM_LLM_API_KEY or OPENAI_API_KEY")
    if not openai_ok:
        reasons.append(
            "openai package missing — pip install 'stock-platform-agents[llm]' "
            f"({openai_err})"
        )
    return {
        "enabled": enabled,
        "hasApiKey": bool(key),
        "openaiImportOk": openai_ok,
        "ready": ready,
        "reasons": reasons,
        "defaultEngine": "deterministic",
        "fallback": _llm_fallback_mode(),
        "maxCalls": _max_calls(),
        "maxTokensSoft": _max_tokens_soft(),
    }


def _llm_fallback_mode() -> str:
    return (
        os.environ.get("STOCK_PLATFORM_LLM_FALLBACK", "deterministic").strip().lower()
        or "deterministic"
    )


def _max_calls() -> int:
    raw = os.environ.get("STOCK_PLATFORM_LLM_MAX_CALLS", "6").strip() or "6"
    try:
        return max(0, int(raw))
    except ValueError:
        return 6


def _max_tokens_soft() -> int | None:
    raw = os.environ.get("STOCK_PLATFORM_LLM_MAX_TOKENS", "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _estimate_tokens(text: str) -> int:
    """Soft char/4 estimate — not a billing meter."""
    return max(0, (len(text) + 3) // 4)


def _truncation_field(metadata: Mapping[str, Any]) -> tuple[str, str] | None:
    for field, truncated_values in _TRUNCATION_MARKERS.items():
        value = metadata.get(field)
        if isinstance(value, str) and value.strip().lower() in truncated_values:
            return field, value
    if str(metadata.get("status", "")).lower() == "incomplete":
        details = metadata.get("incomplete_details") or {}
        reason = details.get("reason") if isinstance(details, Mapping) else None
        if isinstance(reason, str) and reason.strip().lower() in _RESPONSES_INCOMPLETE_REASONS:
            return "incomplete_details.reason", reason
    return None


def warn_if_truncated(response_meta: Mapping[str, Any] | None) -> list[str]:
    """Return warning strings when response metadata indicates output truncation.

    Covers:
    - Anthropic ``stop_reason=max_tokens``
    - OpenAI Chat ``finish_reason=length``
    - Gemini ``finish_reason=MAX_TOKENS`` (case-insensitive via lower())
    - OpenAI Responses ``status=incomplete`` + ``incomplete_details.reason=max_output_tokens``
    """
    if not response_meta:
        return []
    hit = _truncation_field(response_meta)
    if not hit:
        return []
    field, value = hit
    msg = (
        f"LLM response truncated ({field}={value}); raise max_tokens / "
        "STOCK_PLATFORM_LLM_MAX_TOKENS awareness — report may be incomplete."
    )
    warnings.warn(msg, UserWarning, stacklevel=2)
    return [msg]


class _LlmBudget:
    """Per-session call + soft token budget."""

    def __init__(self) -> None:
        self.max_calls = _max_calls()
        self.max_tokens = _max_tokens_soft()
        self.calls = 0
        self.tokens_est = 0

    def before_call(self, system: str, user: str) -> None:
        if self.calls >= self.max_calls:
            raise LlmBudgetExceeded(
                f"LLM call budget exceeded ({self.calls}>={self.max_calls} "
                f"STOCK_PLATFORM_LLM_MAX_CALLS)"
            )
        prompt_est = _estimate_tokens(system) + _estimate_tokens(user)
        if self.max_tokens is not None and self.tokens_est + prompt_est > self.max_tokens:
            raise LlmBudgetExceeded(
                f"LLM soft token budget exceeded "
                f"(est {self.tokens_est + prompt_est}>{self.max_tokens} "
                f"STOCK_PLATFORM_LLM_MAX_TOKENS)"
            )

    def after_call(self, system: str, user: str, content: str) -> None:
        self.calls += 1
        self.tokens_est += (
            _estimate_tokens(system) + _estimate_tokens(user) + _estimate_tokens(content)
        )


def _require_llm_env(*, llm_call: LlmCall | None) -> None:
    if llm_call is not None:
        return
    st = llm_debate_status()
    if st["ready"]:
        return
    raise LlmUnavailableError(
        "LLM debate unavailable (fail-closed): " + "; ".join(st["reasons"])
    )


def _default_openai_call(system: str, user: str) -> str:
    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        raise LlmUnavailableError(
            "openai import failed (fail-closed); "
            "pip install 'stock-platform-agents[llm]'"
        ) from exc
    api_key = (
        os.environ.get("STOCK_PLATFORM_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise LlmUnavailableError("missing LLM API key (fail-closed)")
    model = os.environ.get("STOCK_PLATFORM_LLM_MODEL", "gpt-4o-mini").strip()
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    meta: dict[str, Any] = {}
    try:
        choice0 = resp.choices[0]
        fr = getattr(choice0, "finish_reason", None)
        if fr is not None:
            meta["finish_reason"] = fr
    except Exception:  # noqa: BLE001
        pass
    warn_if_truncated(meta)
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise LlmUnavailableError("empty LLM response (fail-closed)")
    return content


def _parse_llm_payload(text: str) -> dict[str, Any]:
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
    # Loose fallback: parse free-text rating (boundary-aware); default Hold.
    from .rating import parse_rating, to_ternary_verdict

    verdict = to_ternary_verdict(parse_rating(raw, default="Hold"))
    return {
        "bull": "LLM bull thesis unavailable; see judge.",
        "bear": "LLM bear thesis unavailable; see judge.",
        "risk": "LLM risk thesis unavailable; see judge.",
        "verdict": verdict,
        "judge": raw[:2000],
    }


def _normalize_verdict(value: Any) -> Verdict:
    from .rating import parse_rating, to_ternary_verdict

    text = str(value or "").strip()
    if not text:
        return "Hold"
    # Prefer 5-tier boundary-aware parser, then map to debate ternary.
    parsed = parse_rating(text, default="")
    if parsed:
        return to_ternary_verdict(parsed)
    lower = text.lower()
    if lower in {"buy", "long", "overweight"}:
        return "Buy"
    if lower in {"sell", "short", "underweight"}:
        return "Sell"
    return "Hold"


def _maybe_deterministic_fallback(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None,
    lookback_days: int,
    exc: BaseException,
) -> DebateReport:
    mode = _llm_fallback_mode()
    if mode in {"deterministic", "rules", "m12", "1", "true", "yes", "on"}:
        report = build_debate_report(
            provider, symbol, asof=asof, lookback_days=lookback_days
        )
        report.warnings.append(
            f"LLM fallback to deterministic ({type(exc).__name__}: {exc})"
        )
        return report
    if isinstance(exc, LlmUnavailableError):
        raise exc
    raise LlmUnavailableError(f"LLM failed (fail-closed): {exc}") from exc


def build_llm_debate_report(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
    lookback_days: int = 60,
    llm_call: LlmCall | None = None,
    budget: _LlmBudget | None = None,
    response_meta: Mapping[str, Any] | None = None,
) -> DebateReport:
    """Run Bull/Bear/Risk via optional LLM; market data only from ``provider``."""
    _require_llm_env(llm_call=llm_call)
    call = llm_call or _default_openai_call
    session = budget or _LlmBudget()

    code = normalize_symbol(symbol)
    asof_d = _parse_asof(asof)
    warnings_list: list[str] = []
    hist = _historical_warning(asof_d)
    if hist:
        warnings_list.append(hist)

    start = date.fromordinal(max(asof_d.toordinal() - int(lookback_days), 1))
    bars = provider.get_daily([code], start=start, end=asof_d)
    bars = [b for b in bars if str(b.get("date", ""))[:10] <= asof_d.isoformat()]
    if not bars:
        raise AgentError(f"no daily bars for {code} asof {asof_d.isoformat()}")

    if asof_d == date.today():
        try:
            provider.get_realtime([code])
        except Exception as exc:  # noqa: BLE001
            warnings_list.append(f"realtime unavailable: {exc}")
    else:
        warnings_list.append("已跳过 realtime（历史分析日）")

    closes = _closes(bars)
    last_close = closes[-1] if closes else None
    first = closes[0] if closes else None
    ret = ((last_close / first) - 1.0) if first and last_close else 0.0

    system = (
        "You are a research debate assistant for A-share paper trading. "
        "Reply with JSON only: "
        '{"bull":"...","bear":"...","risk":"...","verdict":"Buy|Hold|Sell","judge":"..."}. '
        "Not investment advice. Do not invent prices beyond the provided facts."
    )
    user = (
        f"symbol={code} asof={asof_d.isoformat()} daily_bars={len(bars)} "
        f"last_close={last_close} window_return={ret:.4f}\n"
        f"recent_closes={closes[-10:]}"
    )
    try:
        session.before_call(system, user)
        content = call(system, user)
        session.after_call(system, user, content)
        trunc = warn_if_truncated(response_meta)
        warnings_list.extend(trunc)
        payload = _parse_llm_payload(content)
    except (LlmUnavailableError, LlmBudgetExceeded):
        raise
    except Exception as exc:  # noqa: BLE001
        raise LlmUnavailableError(f"LLM call failed (fail-closed): {exc}") from exc

    verdict = _normalize_verdict(payload.get("verdict"))
    rounds = [
        DebateRound(role="bull", thesis=str(payload.get("bull") or "")),
        DebateRound(role="bear", thesis=str(payload.get("bear") or "")),
        DebateRound(role="risk", thesis=str(payload.get("risk") or "")),
        DebateRound(
            role="judge",
            thesis=str(payload.get("judge") or f"LLM verdict {verdict}"),
        ),
    ]
    # Score placeholder: LLM path does not invent numeric bull/bear; keep zeros + note.
    score = {"bull": 0.0, "bear": 0.0, "risk": 0.0, "net": 0.0}
    if verdict == "Buy":
        score = {"bull": 1.0, "bear": 0.0, "risk": 0.5, "net": 1.0}
    elif verdict == "Sell":
        score = {"bull": 0.0, "bear": 1.0, "risk": 0.5, "net": -1.0}

    return DebateReport(
        symbol=code,
        asof=asof_d.isoformat(),
        provider=getattr(provider, "name", type(provider).__name__),
        rounds=rounds,
        score=score,
        verdict=verdict,
        daily_bars=len(bars),
        last_close=last_close,
        warnings=warnings_list,
        kind="llm_debate",
        disclaimer="模板结论，非投资建议；可选 LLM 辩论路径；数据仅经 MarketDataProvider。",
    )


def run_debate(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
    engine: str = "deterministic",
    llm_call: LlmCall | None = None,
    lookback_days: int = 60,
    budget: _LlmBudget | None = None,
) -> DebateReport:
    """Dispatch deterministic (default) vs optional LLM debate."""
    eng = (engine or "deterministic").strip().lower()
    if eng in {"", "deterministic", "rules", "m12"}:
        return build_debate_report(
            provider, symbol, asof=asof, lookback_days=lookback_days
        )
    if eng in {"llm", "openai"}:
        try:
            return build_llm_debate_report(
                provider,
                symbol,
                asof=asof,
                lookback_days=lookback_days,
                llm_call=llm_call,
                budget=budget,
            )
        except (LlmUnavailableError, LlmBudgetExceeded) as exc:
            return _maybe_deterministic_fallback(
                provider,
                symbol,
                asof=asof,
                lookback_days=lookback_days,
                exc=exc,
            )
    raise AgentError(f"unknown debate engine={engine!r}; use deterministic|llm")


def debate_brief_picks(
    provider: SupportsMarketData,
    brief: Mapping[str, Any],
    *,
    engine: str = "deterministic",
    llm_call: LlmCall | None = None,
    max_picks: int | None = None,
) -> dict[str, Any]:
    """Run debate for each TopN pick after a brief (default deterministic).

    On LLM engine, missing deps/keys / budget / call failure either degrade to
    deterministic (default ``STOCK_PLATFORM_LLM_FALLBACK``) or raise
    ``LlmUnavailableError`` when fallback is fail-closed.
    """
    eng = (engine or "deterministic").strip().lower()
    if eng in {"llm", "openai"}:
        try:
            _require_llm_env(llm_call=llm_call)
        except LlmUnavailableError as exc:
            if _llm_fallback_mode() in {
                "deterministic",
                "rules",
                "m12",
                "1",
                "true",
                "yes",
                "on",
            }:
                eng = "deterministic"
            else:
                raise exc

    asof = brief.get("asof")
    picks = list(brief.get("picks") or [])
    if max_picks is not None:
        picks = picks[: int(max_picks)]
    debates: list[dict[str, Any]] = []
    budget = _LlmBudget() if eng in {"llm", "openai"} else None
    used_engine = "llm" if eng in {"llm", "openai"} else "deterministic"
    for pick in picks:
        sym = str(pick.get("symbol") or "").strip()
        if not sym:
            continue
        report = run_debate(
            provider,
            sym,
            asof=asof,
            engine=eng,
            llm_call=llm_call,
            budget=budget,
        )
        if report.kind != "llm_debate" and eng in {"llm", "openai"}:
            used_engine = "deterministic_fallback"
        debates.append(
            {
                "rank": pick.get("rank"),
                "symbol": report.symbol,
                "debate": report.to_dict(),
            }
        )
    return {
        "brief": dict(brief),
        "engine": used_engine if eng in {"llm", "openai"} else "deterministic",
        "debates": debates,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research debate after TopN; not investment advice.",
    }
