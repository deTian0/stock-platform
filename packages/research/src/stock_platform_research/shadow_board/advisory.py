"""Set B — Bayesian + LLM advisory stubs (never override hard gates)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def advisory_set_b(
    passed: Sequence[Mapping[str, Any]] | None = None,
    *,
    enable: bool = False,
) -> dict[str, Any] | None:
    """Return ``None`` (default) or an experimental advisory placeholder.

    Bayesian priors + LLM win-rate fields are **future work**. When enabled,
    this only attaches non-binding placeholders; callers must not use them to
    admit names that failed Set A.
    """
    if not enable:
        return None
    codes = [str(r.get("code") or "") for r in (passed or []) if r.get("code")]
    return {
        "status": "experimental",
        "excludedFromPerformance": True,
        "bayesian": None,
        "llmWinRate": None,
        "note": "集 B 顾问占位：贝叶斯先验与 LLM 胜率 schema 待 Y1 前实验；不可覆盖硬闸",
        "rankedCodes": codes,
        "cannotAdmitHardRejects": True,
    }


__all__ = ["advisory_set_b"]
