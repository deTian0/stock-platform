"""Optional LLM debate — soft-import / fail-closed; MarketDataProvider only.

Default product path remains ``build_debate_report`` (deterministic, ADR 0017).
This module never embeds Eastmoney URLs; bars come only from the injected provider.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import date
from typing import Any, Callable, Mapping, Protocol

from stock_platform_providers import normalize_symbol

from .debate import DebateReport, DebateRound, Verdict, _closes, build_debate_report
from .errors import AgentError
from .report import SupportsMarketData, _historical_warning, _parse_asof

LlmCall = Callable[[str, str], str]


class LlmUnavailableError(AgentError):
    """Raised when optional LLM deps/keys are missing or the call fails closed."""


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
    }


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
    # Loose fallback: treat whole text as judge thesis, Hold verdict.
    return {
        "bull": "LLM bull thesis unavailable; see judge.",
        "bear": "LLM bear thesis unavailable; see judge.",
        "risk": "LLM risk thesis unavailable; see judge.",
        "verdict": "Hold",
        "judge": raw[:2000],
    }


def _normalize_verdict(value: Any) -> Verdict:
    text = str(value or "Hold").strip().capitalize()
    if text in {"Buy", "Hold", "Sell"}:
        return text  # type: ignore[return-value]
    lower = text.lower()
    if lower in {"buy", "long", "overweight"}:
        return "Buy"
    if lower in {"sell", "short", "underweight"}:
        return "Sell"
    return "Hold"


def build_llm_debate_report(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
    lookback_days: int = 60,
    llm_call: LlmCall | None = None,
) -> DebateReport:
    """Run Bull/Bear/Risk via optional LLM; market data only from ``provider``."""
    _require_llm_env(llm_call=llm_call)
    call = llm_call or _default_openai_call

    code = normalize_symbol(symbol)
    asof_d = _parse_asof(asof)
    warnings: list[str] = []
    hist = _historical_warning(asof_d)
    if hist:
        warnings.append(hist)

    start = date.fromordinal(max(asof_d.toordinal() - int(lookback_days), 1))
    bars = provider.get_daily([code], start=start, end=asof_d)
    bars = [b for b in bars if str(b.get("date", ""))[:10] <= asof_d.isoformat()]
    if not bars:
        raise AgentError(f"no daily bars for {code} asof {asof_d.isoformat()}")

    if asof_d == date.today():
        try:
            provider.get_realtime([code])
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"realtime unavailable: {exc}")
    else:
        warnings.append("已跳过 realtime（历史分析日）")

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
        payload = _parse_llm_payload(call(system, user))
    except LlmUnavailableError:
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
        warnings=warnings,
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
) -> DebateReport:
    """Dispatch deterministic (default) vs optional LLM debate."""
    eng = (engine or "deterministic").strip().lower()
    if eng in {"", "deterministic", "rules", "m12"}:
        return build_debate_report(
            provider, symbol, asof=asof, lookback_days=lookback_days
        )
    if eng in {"llm", "openai"}:
        return build_llm_debate_report(
            provider,
            symbol,
            asof=asof,
            lookback_days=lookback_days,
            llm_call=llm_call,
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

    On LLM engine, missing deps/keys raise ``LlmUnavailableError`` before any
    silent degradation — callers must not pretend brief failed.
    """
    eng = (engine or "deterministic").strip().lower()
    if eng in {"llm", "openai"}:
        _require_llm_env(llm_call=llm_call)

    asof = brief.get("asof")
    picks = list(brief.get("picks") or [])
    if max_picks is not None:
        picks = picks[: int(max_picks)]
    debates: list[dict[str, Any]] = []
    for pick in picks:
        sym = str(pick.get("symbol") or "").strip()
        if not sym:
            continue
        report = run_debate(
            provider, sym, asof=asof, engine=eng, llm_call=llm_call
        )
        debates.append(
            {
                "rank": pick.get("rank"),
                "symbol": report.symbol,
                "debate": report.to_dict(),
            }
        )
    return {
        "brief": dict(brief),
        "engine": "llm" if eng in {"llm", "openai"} else "deterministic",
        "debates": debates,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research debate after TopN; not investment advice.",
    }
