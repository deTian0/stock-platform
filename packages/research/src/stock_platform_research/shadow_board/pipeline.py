"""End-to-end shadow board pipeline (Round1 → Round2 A → Final → ledger)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence  # Any used for optional DI hooks

from .advisory import advisory_set_b
from .ledger import write_shadow_ledger
from .round2 import apply_round2_set_a
from .schools import run_round1

REQUIRED_REASON_FIELDS = ("holdingPeriod", "trigger", "expectation", "invalidation")


def _validate_structured_reasons(
    rows: Sequence[Mapping[str, Any]],
    *,
    llm_path: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep rows with required fields; on LLM path missing fields → degrade drop."""
    kept: list[dict[str, Any]] = []
    degraded: list[dict[str, Any]] = []
    for row in rows:
        missing = [f for f in REQUIRED_REASON_FIELDS if not str(row.get(f) or "").strip()]
        if missing:
            item = dict(row)
            item["degradeReason"] = f"结构化理由缺字段: {', '.join(missing)}"
            degraded.append(item)
            if llm_path:
                continue
            # Rule-only MVP should already fill fields; still fail-closed if not.
            continue
        kept.append(dict(row))
    return kept, degraded


def run_shadow_board(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    asof: str | None = None,
    top_k: int = 8,
    shadow_dir: Path | str | None = None,
    write: bool = True,
    enable_advisory_b: bool = False,
    llm_path: bool = False,
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
    final, degraded = _validate_structured_reasons(passed, llm_path=llm_path)
    advisory = advisory_set_b(final, enable=enable_advisory_b)

    if final:
        status = "ok"
    elif degraded and llm_path:
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
