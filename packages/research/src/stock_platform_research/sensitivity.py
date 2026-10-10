"""Gate parameter sensitivity sweep — the ``S3`` single definition.

Why this module exists
----------------------
``S1`` made a gate change *expressible* in a strategy config; ``S2`` admitted new
factors through an IC/ICIR gate. Neither answered the question the roadmap's
``S3`` raises: *does the chosen gate value sit on a broad plateau, or is it a
lucky single point?* A lone optimum is the classic signature of a curve-fit; a
smooth plateau is what an edge that is structural rather than tuned looks like.

This module is the **single definition** of that sweep. Three functions, no I/O:

* :func:`sweep_entry_gate` — move **one** gate knob over a grid and replay the
  whole book for each value through the *same* engine
  (:func:`book_replay.replay_book`, the ``X4`` single definition) entered via the
  *same* provider (:func:`book_replay.screener_entry_provider`), so two sweep
  points differ only by the knob.
* :func:`summarize_sweep` — turn the grid into a **robust-range verdict**:
  ``robust`` (a plateau of ≥2 adjacent points within tolerance), ``fragile`` (a
  single lucky point), ``flat`` (the knob barely moves the objective) or
  ``insufficient`` (fewer than three usable points).
* :func:`build_sensitivity_report` — sweep several knobs and roll the verdicts up
  into one overall read.

Data in, numbers out. SIMULATE only. ``liveTradingEnabled=False``. Not investment
advice.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Mapping, Sequence

import pandas as pd

from .book_replay import ReplayParams, replay_book, screener_entry_provider
from .gates import EntryGateParams
from .portfolio import compute_metrics

# The gate constants a sweep may move. ``reversal_q`` / ``ma_band`` are
# ``EntryGateParams`` fields; ``min_pick_score`` is the provider's score floor.
SWEEP_KNOBS = ("reversal_q", "min_pick_score", "ma_band")

# Default grids — five points each, straddling the shipped default so a plateau
# verdict is decided by the *shape* around it, not by an endpoint.
DEFAULT_GRIDS: dict[str, tuple[float, ...]] = {
    "reversal_q": (0.10, 0.20, 0.30, 0.40, 0.50),
    "min_pick_score": (0.50, 0.60, 0.70, 0.80, 0.90),
    "ma_band": (0.88, 0.90, 0.93, 0.96, 0.98),
}

# Which way each objective is "better". Everything else defaults to ``max``.
OBJECTIVE_DIRECTION: dict[str, str] = {
    "sharpe": "max",
    "sortino": "max",
    "calmar": "max",
    "total_return": "max",
    "cagr": "max",
    "win_rate": "max",
    "max_drawdown": "min",
}

DEFAULT_OBJECTIVE = "sharpe"
DEFAULT_TOLERANCE = 0.10
MIN_ROBUST_POINTS = 2
_EPS = 1e-12

VERDICTS = ("robust", "fragile", "flat", "insufficient")


def gate_params_for(
    knob: str, value: float, base: EntryGateParams | None = None
) -> EntryGateParams:
    """Return ``base`` with the one field ``knob`` moved to ``value``.

    ``min_pick_score`` is not an ``EntryGateParams`` field (it is the provider's
    score floor), so it returns ``base`` untouched — the caller routes it to the
    floor instead.
    """
    p = base if base is not None else EntryGateParams()
    if knob == "reversal_q":
        return replace(p, reversal_q=float(value))
    if knob == "ma_band":
        return replace(p, ma20_band=float(value), ma60_band=float(value))
    if knob == "min_pick_score":
        return p
    raise ValueError(f"unknown sweep knob: {knob!r} (expected one of {SWEEP_KNOBS})")


def score_floor_for(knob: str, value: float, base_floor: float = 0.80) -> float:
    """The score floor for one sweep point (only ``min_pick_score`` moves it)."""
    return float(value) if knob == "min_pick_score" else float(base_floor)


def sweep_entry_gate(
    feats: pd.DataFrame,
    *,
    knob: str,
    values: Sequence[float],
    base_params: EntryGateParams | None = None,
    min_pick_score: float = 0.80,
    weights: Mapping[str, float] | None = None,
    value_factor: bool = False,
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """Replay ``feats`` once per grid value of ``knob``; return the raw points.

    ``feats`` is an already-built feature frame (:func:`backtest.prepare_book_frame`).
    Building it **once** and reusing it across points is the whole point: the only
    thing that changes between two points is the gate, so the equity curves are
    comparable without re-normalisation. Fail-closed: an unknown knob or an empty
    grid raises rather than returning a fabricated plateau.
    """
    knob = str(knob)
    if knob not in SWEEP_KNOBS:
        raise ValueError(f"unknown sweep knob: {knob!r} (expected one of {SWEEP_KNOBS})")
    grid = tuple(float(v) for v in values)
    if not grid:
        raise ValueError("values must be a non-empty grid")

    base = base_params if base_params is not None else EntryGateParams()
    initial = (params or ReplayParams()).initial_capital

    points: list[dict[str, Any]] = []
    for v in grid:
        gp = gate_params_for(knob, v, base)
        floor = score_floor_for(knob, v, min_pick_score)
        loop = replay_book(
            feats,
            entry_provider=screener_entry_provider(
                min_pick_score=floor,
                weights=weights,
                value_factor=value_factor,
                gate_params=gp,
            ),
            params=params,
        )
        metrics = compute_metrics(
            loop["equity_curve"], loop["trades"], initial_capital=initial
        )
        points.append(
            {
                "value": v,
                "nTrades": len(loop["trades"] or []),
                "finalEquity": loop["final_equity"],
                "metrics": metrics,
                "effective": {"gateParams": asdict(gp), "minPickScore": floor},
            }
        )

    return {
        "ok": True,
        "knob": knob,
        "values": list(grid),
        "points": points,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


def summarize_sweep(
    points: Sequence[Mapping[str, Any]],
    *,
    objective: str = DEFAULT_OBJECTIVE,
    direction: str | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    min_plateau: int = MIN_ROBUST_POINTS,
) -> dict[str, Any]:
    """Turn a sweep into a robust-range verdict (``S3``).

    A point is *in the plateau* when its objective is within ``tolerance`` of the
    best — measured **relative to the best value** (``tolerance * |best|``) so the
    same number works for a sharpe near 1 and a return near 0.5. The
    ``robustRange`` is the **contiguous** run of grid values around the best that
    all stay inside that band; a run shorter than ``min_plateau`` means the optimum
    is a lone spike (``fragile``) rather than a plateau (``robust``).

    Verdicts: ``insufficient`` (<3 usable points) → ``flat`` (the grid barely moves
    the objective) → ``robust`` / ``fragile``. Never invents a best when every
    point is missing (that is ``insufficient`` with ``best=None``).
    """
    dir_ = direction or OBJECTIVE_DIRECTION.get(objective, "max")
    sign = 1.0 if dir_ == "max" else -1.0

    usable: list[tuple[float, float]] = []
    for pt in points:
        metrics = pt.get("metrics") or {}
        raw = metrics.get(objective)
        if raw is None:
            continue
        try:
            usable.append((float(pt.get("value")), float(raw)))
        except (TypeError, ValueError):
            continue
    usable.sort(key=lambda t: t[0])
    n = len(usable)

    base: dict[str, Any] = {
        "objective": objective,
        "direction": dir_,
        "tolerance": tolerance,
        "nPoints": n,
    }
    if n < 3:
        return {
            **base,
            "verdict": "insufficient",
            "best": None,
            "bestObjective": None,
            "plateau": [],
            "robustRange": None,
            "stability": None,
            "monotonic": 0,
            "spread": None,
            "note": "可用网格点不足 3 个，无法判断稳健性。",
        }

    vals = [v for v, _ in usable]
    objs = [o for _, o in usable]
    spread = max(objs) - min(objs)
    best_i = max(range(n), key=lambda i: sign * objs[i])
    best_v, best_o = vals[best_i], objs[best_i]

    if spread <= _EPS:
        return {
            **base,
            "verdict": "flat",
            "best": best_v,
            "bestObjective": best_o,
            "plateau": list(vals),
            "robustRange": {"lo": vals[0], "hi": vals[-1], "n": n},
            "stability": 1.0,
            "monotonic": 0,
            "spread": spread,
            "note": "网格内目标函数几乎不变；该闸门对目标不敏感，任一取值皆可。",
        }

    tol_abs = float(tolerance) * abs(best_o) if abs(best_o) > _EPS else float(tolerance)

    def inside(i: int) -> bool:
        return sign * (objs[i] - best_o) >= -tol_abs

    plateau = [v for v, o in usable if sign * (o - best_o) >= -tol_abs]
    lo_i = best_i
    while lo_i - 1 >= 0 and inside(lo_i - 1):
        lo_i -= 1
    hi_i = best_i
    while hi_i + 1 < n and inside(hi_i + 1):
        hi_i += 1
    span_len = hi_i - lo_i + 1
    stability = len(plateau) / n

    steps = [
        1 if objs[i + 1] - objs[i] > _EPS else (-1 if objs[i + 1] - objs[i] < -_EPS else 0)
        for i in range(n - 1)
    ]
    signs = {s for s in steps if s}
    monotonic = signs.pop() if len(signs) == 1 else 0

    if span_len >= min_plateau:
        verdict = "robust"
        note = (
            f"{span_len} 个相邻网格点落在最优 {tolerance:.0%} 容差内"
            f"（稳健区间 {vals[lo_i]}–{vals[hi_i]}）；最优非单点，过拟合风险低。"
        )
    else:
        verdict = "fragile"
        note = (
            f"仅最优单点 {best_v} 落在容差内；相邻点即劣化，"
            "该取值疑为曲线拟合，不宜据此定档。"
        )

    return {
        **base,
        "verdict": verdict,
        "best": best_v,
        "bestObjective": best_o,
        "plateau": plateau,
        "robustRange": {"lo": vals[lo_i], "hi": vals[hi_i], "n": span_len},
        "stability": round(stability, 4),
        "monotonic": monotonic,
        "spread": spread,
        "note": note,
    }


def build_sensitivity_report(
    feats: pd.DataFrame,
    *,
    knobs: Sequence[str] | None = None,
    grids: Mapping[str, Sequence[float]] | None = None,
    objective: str = DEFAULT_OBJECTIVE,
    tolerance: float = DEFAULT_TOLERANCE,
    direction: str | None = None,
    base_params: EntryGateParams | None = None,
    min_pick_score: float = 0.80,
    weights: Mapping[str, float] | None = None,
    value_factor: bool = False,
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """Sweep several knobs and roll the verdicts into one overall read (``S3``).

    Overall precedence: any ``insufficient`` → ``insufficient``; else any
    ``fragile`` → ``fragile`` (a gate whose chosen value is a lone spike must not
    be quietly trusted); else any ``robust`` → ``robust``; else ``flat``.
    """
    knob_list = list(knobs) if knobs else list(SWEEP_KNOBS)
    grid_map = dict(grids or {})

    knobs_out: dict[str, Any] = {}
    verdicts: dict[str, str] = {}
    for knob in knob_list:
        values = grid_map.get(knob, DEFAULT_GRIDS.get(knob))
        if values is None:
            raise ValueError(f"no default grid for knob {knob!r}; pass grids={{...}}")
        sweep = sweep_entry_gate(
            feats,
            knob=knob,
            values=values,
            base_params=base_params,
            min_pick_score=min_pick_score,
            weights=weights,
            value_factor=value_factor,
            params=params,
        )
        summary = summarize_sweep(
            sweep["points"],
            objective=objective,
            direction=direction,
            tolerance=tolerance,
        )
        knobs_out[knob] = {"points": sweep["points"], "summary": summary}
        verdicts[knob] = summary["verdict"]

    buckets: dict[str, list[str]] = {v: [] for v in VERDICTS}
    for knob, verdict in verdicts.items():
        buckets.setdefault(verdict, []).append(knob)

    if not verdicts or buckets.get("insufficient"):
        overall = "insufficient"
    elif buckets.get("fragile"):
        overall = "fragile"
    elif buckets.get("robust"):
        overall = "robust"
    else:
        overall = "flat"

    return {
        "ok": True,
        "objective": objective,
        "tolerance": tolerance,
        "knobs": knobs_out,
        "verdicts": verdicts,
        "robust": buckets["robust"],
        "fragile": buckets["fragile"],
        "flat": buckets["flat"],
        "insufficient": buckets["insufficient"],
        "overall": overall,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": (
            "闸门敏感性扫描：每点走同一 book_replay 引擎，仅旋钮不同；"
            "稳健=最优非单点，脆弱=仅最优点达标（过拟合风险）。"
        ),
        "disclaimer": "Research only; not investment advice.",
    }


__all__ = [
    "DEFAULT_GRIDS",
    "DEFAULT_OBJECTIVE",
    "DEFAULT_TOLERANCE",
    "MIN_ROBUST_POINTS",
    "OBJECTIVE_DIRECTION",
    "SWEEP_KNOBS",
    "VERDICTS",
    "build_sensitivity_report",
    "gate_params_for",
    "score_floor_for",
    "summarize_sweep",
    "sweep_entry_gate",
]
