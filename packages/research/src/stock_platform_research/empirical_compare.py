"""Compare engine empirical JSON baselines with platform walk-forward summaries.

Read-only field mapping — does **not** schedule a-stock-engine or pull market data.
"""

from __future__ import annotations

from typing import Any


def _pct_to_fraction(value: Any) -> float | None:
    """Engine ``*_pct`` fields are percentage points → fraction."""
    if value is None:
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def extract_engine_fold_returns(engine_payload: dict[str, Any]) -> dict[str, float]:
    """Map ``folds.<label>.return_pct`` → fraction returns (label preserved).

    Engine field is named ``return_pct`` — always treat as percentage points.
    """
    folds = engine_payload.get("folds") or {}
    out: dict[str, float] = {}
    if not isinstance(folds, dict):
        return out
    for label, row in folds.items():
        if not isinstance(row, dict):
            continue
        raw = row.get("return_pct")
        if raw is None:
            continue
        try:
            out[str(label)] = round(float(raw) / 100.0, 6)
        except (TypeError, ValueError):
            continue
    return out


def compare_empirical_baseline(
    engine_payload: dict[str, Any],
    platform_summary: dict[str, Any],
    *,
    tolerance: float = 0.02,
) -> dict[str, Any]:
    """Side-by-side metrics; never invents agreement when fields are missing.

    ``platform_summary`` may be the inner ``summary`` dict from
    ``summarize_walk_forward`` or a wrapper containing ``summary``.
    """
    if not isinstance(engine_payload, dict):
        raise ValueError("engine_payload must be a dict")
    if not isinstance(platform_summary, dict):
        raise ValueError("platform_summary must be a dict")

    summary = platform_summary.get("summary")
    if isinstance(summary, dict):
        plat = summary
    else:
        plat = platform_summary

    cal = engine_payload.get("calibration") or {}
    if not isinstance(cal, dict):
        cal = {}

    eng_ret = None
    if cal.get("return_pct") is not None:
        try:
            eng_ret = float(cal["return_pct"]) / 100.0
        except (TypeError, ValueError):
            eng_ret = None
    eng_mdd = None
    if cal.get("max_drawdown_pct") is not None:
        try:
            eng_mdd = float(cal["max_drawdown_pct"]) / 100.0
        except (TypeError, ValueError):
            eng_mdd = None

    plat_ret: float | None = None
    if plat.get("compounded_oos_return") is not None:
        try:
            plat_ret = float(plat["compounded_oos_return"])
        except (TypeError, ValueError):
            plat_ret = None

    eng_sharpe = cal.get("sharpe")
    try:
        eng_sharpe_f = float(eng_sharpe) if eng_sharpe is not None else None
    except (TypeError, ValueError):
        eng_sharpe_f = None

    delta_ret: float | None = None
    within = False
    if eng_ret is not None and plat_ret is not None:
        delta_ret = round(plat_ret - eng_ret, 6)
        within = abs(delta_ret) <= tolerance

    fold_returns = extract_engine_fold_returns(engine_payload)
    return {
        "ok": True,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "dualSchedule": False,
        "engine": {
            "calibration_return": eng_ret,
            "calibration_max_drawdown": eng_mdd,
            "calibration_sharpe": eng_sharpe_f,
            "n_folds": len(fold_returns),
            "fold_returns": fold_returns,
        },
        "platform": {
            "compounded_oos_return": plat_ret,
            "avg_oos_objective": plat.get("avg_oos_objective"),
            "degradation": plat.get("degradation"),
            "consistency": plat.get("consistency"),
            "n_folds": plat.get("n_folds"),
        },
        "delta_compounded_return": delta_ret,
        "within_tolerance": within,
        "tolerance": tolerance,
        "note": (
            "只读对照；引擎百分数已归一为小数。"
            "差异常见于宇宙/费用/复权/折切，禁止双调度引擎仓。"
        ),
        "disclaimer": "Research compare only; not investment advice.",
    }
