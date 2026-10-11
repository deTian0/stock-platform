"""Debate lane — optional debate as an **advisory sidecar** on the main path (S5).

The lane brings the optional LLM / deterministic debate into the *main* daily path
(pipeline + CLI + Workbench) **without** letting a verdict leak into the
recommendation accounting. Two hard properties, both asserted in the tests:

1. **Read-only over the brief** — the lane never mutates ``brief["picks"]``; it only
   reads the picks/asof. The picks the brief carries are the same picks after the
   lane runs.
2. **Excluded from performance** — a debate verdict is *not* a rating. It never
   becomes a picks-ledger row, a hit-cycle entry, or a performance-JSONL decision
   (``excludedFromPerformance=True``). A wrong LLM call therefore cannot corrupt
   ``direction_accuracy`` (aligned with the M-A2 rating-boundary 口径).

Engines (default ``off`` → zero LLM, zero side effects):

- ``off``            — no debate at all (default); the lane is a no-op.
- ``deterministic``  — ``build_debate_report`` (ADR 0017); no key, no network.
- ``llm``            — ``build_llm_debate_report`` (ADR 0034) with the ADR 0045
  budget / truncation / degradation guarantees; missing deps → non-silent degrade
  to deterministic (``STOCK_PLATFORM_LLM_FALLBACK=deterministic``, the default) or
  fail-closed when set otherwise.
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import AgentError
from .llm_debate import LlmBudget, run_debate

#: Engines accepted by the lane (``off`` is the product default).
DEBATE_LANE_ENGINES: tuple[str, ...] = ("off", "deterministic", "llm")

_OFF = "off"
_DETERMINISTIC_ALIASES = {"deterministic", "rules", "m12"}
_LLM_ALIASES = {"llm", "openai"}
_OFF_ALIASES = {"", "off", "none", "disabled", "no"}


def normalize_lane_engine(engine: str | None) -> str:
    """Map a loose engine string onto one of :data:`DEBATE_LANE_ENGINES`.

    Raises :class:`AgentError` for anything unknown — callers should turn that into
    a 400 (bad request), never a silent default.
    """
    eng = (engine or _OFF).strip().lower()
    if eng in _OFF_ALIASES:
        return _OFF
    if eng in _DETERMINISTIC_ALIASES:
        return "deterministic"
    if eng in _LLM_ALIASES:
        return "llm"
    raise AgentError(
        f"unknown debate lane engine={engine!r}; use one of {DEBATE_LANE_ENGINES}"
    )


def attach_debate_lane(
    provider: Any,
    brief: Mapping[str, Any],
    *,
    engine: str | None = _OFF,
    max_picks: int | None = None,
    budget: LlmBudget | None = None,
    llm_call: Any = None,
) -> dict[str, Any]:
    """Attach an advisory debate lane to ``brief``'s TopN picks.

    Returns a **lane payload** (not the brief). The brief is only read — callers can
    assert the picks are unchanged. ``budget`` is an explicit :class:`LlmBudget`;
    when omitted it falls back to the env-derived defaults (ADR 0045).
    """
    eng = normalize_lane_engine(engine)
    lane_budget = budget if budget is not None else LlmBudget()
    picks = list(brief.get("picks") or [])
    if max_picks is not None:
        picks = picks[: max(0, int(max_picks))]

    lane: dict[str, Any] = {
        "enabled": eng != _OFF,
        "engine": eng,
        "requestedEngine": eng,
        "asof": brief.get("asof"),
        "picksConsidered": len(picks),
        "debates": [],
        "debateCount": 0,
        "warnings": [],
        "degraded": False,
        "advisory": True,
        "excludedFromPerformance": True,
        "budget": lane_budget.to_dict(),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": (
            "辩论为只读顾问侧车：不进选股/绩效/命中账本；非投资建议。"
        ),
    }
    if eng == _OFF:
        lane["note"] = "debate lane off (default): deterministic picks only, zero LLM."
        return lane

    for pick in picks:
        sym = str(pick.get("symbol") or "").strip()
        if not sym:
            continue
        try:
            report = run_debate(
                provider,
                sym,
                asof=brief.get("asof"),
                engine=eng,
                llm_call=llm_call,
                budget=lane_budget,
            )
        except AgentError as exc:  # per-pick failure never aborts the lane
            lane["warnings"].append(f"{sym}: {exc}")
            continue
        if eng == "llm" and report.kind != "llm_debate":
            lane["degraded"] = True
            lane["engine"] = "deterministic"
        lane["debates"].append(
            {
                "rank": pick.get("rank"),
                "symbol": report.symbol,
                "debate": report.to_dict(),
            }
        )

    lane["debateCount"] = len(lane["debates"])
    lane["budget"] = lane_budget.to_dict()
    return lane


def debate_lane_summary(lane: Mapping[str, Any]) -> dict[str, Any]:
    """Trim a lane payload for manifests: keep counts/verdicts, drop round text."""
    verdicts: list[dict[str, Any]] = []
    for item in lane.get("debates") or []:
        report = (item or {}).get("debate") or {}
        verdicts.append(
            {
                "rank": item.get("rank"),
                "symbol": item.get("symbol"),
                "verdict": report.get("verdict"),
                "kind": report.get("kind"),
                "warningCount": len(report.get("warnings") or []),
            }
        )
    out = {k: v for k, v in lane.items() if k not in {"debates"}}
    out["debateCount"] = len(lane.get("debates") or [])
    out["verdicts"] = verdicts
    return out


__all__ = [
    "DEBATE_LANE_ENGINES",
    "attach_debate_lane",
    "debate_lane_summary",
    "normalize_lane_engine",
]
