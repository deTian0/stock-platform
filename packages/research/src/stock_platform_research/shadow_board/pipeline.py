"""End-to-end shadow board pipeline (Round1 → Round2 A → Final → ledger)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence  # Any used for optional DI hooks

from .advisory import advisory_set_b
from .ledger import write_shadow_ledger
from .reasons import REQUIRED_REASON_FIELDS, ReasonProvider, apply_reason_policy
from .round2 import apply_round2_set_a
from .schools import run_round1


def run_shadow_board(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    asof: str | None = None,
    top_k: int = 8,
    shadow_dir: Path | str | None = None,
    write: bool = True,
    enable_advisory_b: bool = False,
    llm_path: bool = False,
    reason_provider: ReasonProvider | Mapping[str, Mapping[str, Any]] | None = None,
    regime: Mapping[str, bool] | None = None,
    index_bars: Sequence[Mapping[str, Any]] | None = None,
    concept_blocks: Any = None,
    sector_fund_flow: Any = None,
    lhb: Any = None,
    unlock: Any = None,
    **hooks: Any,
) -> dict[str, Any]:
    """Build Final Board payload; optionally write shadow ledger only."""
    day = asof or date.today().isoformat()
    schools = run_round1(
        universe,
        top_k=top_k,
        asof=day,
        regime=regime,
        index_bars=index_bars,
        concept_blocks=concept_blocks,
        sector_fund_flow=sector_fund_flow,
        lhb=lhb,
        unlock=unlock,
        **hooks,
    )
    round2 = apply_round2_set_a(schools)
    passed = list(round2.get("passed") or [])
    # LLM reasons (if injected) may only rewrite the text of names Set A already
    # passed; invalid / vacuous LLM text falls back to the deterministic reason.
    final, degraded, reason_stats = apply_reason_policy(
        passed, reason_provider=reason_provider
    )
    advisory = advisory_set_b(final, enable=enable_advisory_b)

    llm_degraded = bool(reason_stats.get("llmFallback"))
    if final and not llm_degraded:
        status = "ok"
    elif final and llm_degraded:
        status = "degraded"
    elif degraded and (llm_path or reason_provider is not None):
        status = "degraded"
    else:
        status = "empty"

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "asof": day,
        "status": status,
        "excludedFromPerformance": True,
        "shadowOnly": True,
        "arbiter": "set_a",
        "schools": schools,
        "round2": round2,
        "advisoryB": advisory,
        "finalBoard": final,
        "degradedReasons": degraded,
        "reasonStats": reason_stats,
        "notes": [
            "影子链产物；不写生产 picks / hits / 主绩效 JSONL",
            "升级须经 Y1 采纳闸门 → 人工签核 → Y2；禁止跳过",
            "集 B / LLM 恒 excludedFromPerformance，不可覆盖硬闸",
        ],
    }

    if write:
        paths = write_shadow_ledger(payload, shadow_dir=shadow_dir, asof=day)
        payload["ledgerPath"] = paths["json"]
        payload["ledgerJsonl"] = paths["jsonl"]
    else:
        payload["ledgerPath"] = None
        payload["ledgerJsonl"] = None

    return payload


__all__ = ["REQUIRED_REASON_FIELDS", "run_shadow_board"]
