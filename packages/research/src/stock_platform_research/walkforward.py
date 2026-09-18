"""Walk-forward fold split + OOS summary (M-R2; TSP semantics, pure Python).

Aligned with tick-stock-panel ``backtest/walkforward.py``:

- ``generate_folds``: test window starts the **calendar day after** train_end
  (prevents same-bar leakage on closed intervals).
- ``aggregate_oos``: only **valid** folds (caller must filter); never disguise
  invalid folds as zero return.

Does **not** pull market data itself — fold objective values are supplied by the
caller (e.g. PIT long-only wrappers). Not inserted into the daily brief path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Sequence


@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("train_start", "train_end", "test_start", "test_end"):
            d[k] = d[k].isoformat()
        return d


def generate_folds(
    start: date,
    end: date,
    train_days: int,
    test_days: int,
    step_days: int,
) -> list[WalkForwardFold]:
    """Rolling calendar-day folds; test starts at ``train_end + 1 day``."""
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days / test_days / step_days 必须为正")
    if end < start:
        raise ValueError("end 不得早于 start")

    folds: list[WalkForwardFold] = []
    i = 0
    train_start = start
    while True:
        train_end = train_start + timedelta(days=train_days)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days)
        if test_end > end:
            break
        folds.append(
            WalkForwardFold(i, train_start, train_end, test_start, test_end)
        )
        i += 1
        train_start = train_start + timedelta(days=step_days)

    if not folds:
        raise ValueError(
            f"数据区间不足以切出至少一折（需 train+test≥{train_days + test_days} 天，"
            f"实有 {(end - start).days} 天）"
        )
    return folds


def _norm(v: float, direction: str) -> float:
    return -v if direction == "min" else v


def aggregate_oos(
    fold_records: Sequence[dict[str, Any]],
    objective: str = "total_return",
    direction: str = "max",
) -> dict[str, Any]:
    """Aggregate **valid** fold records into compounded OOS / degradation / consistency.

    Each record must include:

    - ``index``, ``test_end``
    - ``is_score`` (float)
    - ``oos_objective`` (float)
    - ``oos_stats.total_return`` (float; used for compounding & consistency)

    Empty input → ``n_folds=0`` with null degradation (not fake 0% edge).
    """
    n = len(fold_records)
    if n == 0:
        return {
            "n_folds": 0,
            "objective": objective,
            "direction": direction,
            "compounded_oos_return": 0.0,
            "avg_is_objective": None,
            "avg_oos_objective": None,
            "degradation": None,
            "consistency": 0.0,
            "oos_equity_curve": [],
        }

    equity = 1.0
    curve: list[dict[str, Any]] = []
    n_positive = 0
    for f in fold_records:
        stats = f.get("oos_stats") or {}
        r = float(stats.get("total_return", 0.0) or 0.0)
        equity *= 1.0 + r
        if r > 0:
            n_positive += 1
        curve.append(
            {
                "fold": f["index"],
                "date": str(f.get("test_end", "")),
                "value": round(equity, 4),
            }
        )

    is_vals = [float(f["is_score"]) for f in fold_records if f.get("is_score") is not None]
    oos_vals = [
        float(f["oos_objective"])
        for f in fold_records
        if f.get("oos_objective") is not None
    ]
    avg_is = round(sum(is_vals) / len(is_vals), 4) if is_vals else None
    avg_oos = round(sum(oos_vals) / len(oos_vals), 4) if oos_vals else None
    degradation = (
        round(_norm(avg_is, direction) - _norm(avg_oos, direction), 4)
        if avg_is is not None and avg_oos is not None
        else None
    )

    return {
        "n_folds": n,
        "objective": objective,
        "direction": direction,
        "compounded_oos_return": round(equity - 1.0, 4),
        "avg_is_objective": avg_is,
        "avg_oos_objective": avg_oos,
        "degradation": degradation,
        "consistency": round(n_positive / n, 4),
        "oos_equity_curve": curve,
    }


def summarize_walk_forward(
    *,
    start: date,
    end: date,
    train_days: int,
    test_days: int,
    step_days: int,
    fold_records: Sequence[dict[str, Any]] | None = None,
    objective: str = "total_return",
    direction: str = "max",
) -> dict[str, Any]:
    """Build fold plan + optional OOS summary (fail-closed on empty valid folds)."""
    folds = generate_folds(start, end, train_days, test_days, step_days)
    valid = [dict(r) for r in (fold_records or []) if r]
    # Reject records that look like padded zeros without scores.
    cleaned: list[dict[str, Any]] = []
    for r in valid:
        if r.get("is_score") is None or r.get("oos_objective") is None:
            continue
        if r.get("error"):
            continue
        cleaned.append(r)

    summary = aggregate_oos(cleaned, objective=objective, direction=direction)
    return {
        "ok": True,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "folds": [f.as_dict() for f in folds],
        "n_planned_folds": len(folds),
        "n_valid_folds": summary["n_folds"],
        "summary": summary,
        "note": (
            "Walk-forward 摘要内核；不进每日 brief 主路径。"
            "无效折不得伪装成 0 收益混入汇总。"
        ),
        "disclaimer": "Research only; not investment advice.",
    }
