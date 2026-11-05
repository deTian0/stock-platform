"""Set B — Bayesian + LLM advisory stubs (never override hard gates)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .round2 import SCHOOL_PRIORITY

_PRIORITY_BONUS = {sid: float(len(SCHOOL_PRIORITY) - i) * 0.01 for i, sid in enumerate(SCHOOL_PRIORITY)}


def advisory_set_b(
    passed: Sequence[Mapping[str, Any]] | None = None,
    *,
    enable: bool = False,
) -> dict[str, Any] | None:
    """Return ``None`` (default) or an experimental advisory placeholder.

    Bayesian priors + LLM win-rate fields remain **future work**. When enabled,
    attach non-binding rank hints (school-priority tie-break only). Callers must
    not use them to admit names that failed Set A.
    """
    if not enable:
        return None
    rows = [r for r in (passed or []) if isinstance(r, Mapping) and r.get("code")]
    ranked = sorted(
        rows,
        key=lambda r: (
            -(_PRIORITY_BONUS.get(str(r.get("school") or ""), 0.0)),
            -float(r.get("score") or 0.0),
            str(r.get("code") or ""),
        ),
    )
    codes = [str(r.get("code") or "") for r in ranked]
    hints = [
        {
            "code": str(r.get("code") or ""),
            "school": r.get("school"),
            "advisoryScore": round(
                float(r.get("score") or 0.0)
                + _PRIORITY_BONUS.get(str(r.get("school") or ""), 0.0),
                6,
            ),
            "note": "顾问排序提示；不可覆盖硬闸",
        }
        for r in ranked
    ]
    return {
        "status": "experimental",
        "excludedFromPerformance": True,
        "bayesian": None,
        "llmWinRate": None,
        "note": "集 B 顾问占位：学校优先级轻微加权排序；贝叶斯/LLM 胜率 schema 待 Y1 前实验；不可覆盖硬闸",
        "rankedCodes": codes,
        "rankHints": hints,
        "cannotAdmitHardRejects": True,
    }


__all__ = ["advisory_set_b"]
