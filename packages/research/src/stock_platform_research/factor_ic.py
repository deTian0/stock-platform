"""Cross-sectional rank IC helper (M-R4 thin slice).

Pure in-memory Spearman IC (no scipy); no HTTP / no dual pipeline.
Not on the daily brief path.
"""

from __future__ import annotations

from typing import Any, Sequence


def _rankdata(values: Sequence[float]) -> list[float]:
    """Average ranks for ties (1-based)."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx2 = 0.0
    dy2 = 0.0
    for x, y in zip(xs, ys, strict=True):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    if dx2 <= 0.0 or dy2 <= 0.0:
        return None
    return num / (dx2**0.5 * dy2**0.5)


def spearman_rank_ic(
    factor: Sequence[float | None],
    forward_return: Sequence[float | None],
) -> float | None:
    """Spearman correlation between factor and forward return; None if < 3 pairs."""
    if len(factor) != len(forward_return):
        raise ValueError("factor and forward_return length mismatch")
    rows = [
        (float(f), float(r))
        for f, r in zip(factor, forward_return, strict=True)
        if f is not None and r is not None
    ]
    if len(rows) < 3:
        return None
    fx = [r[0] for r in rows]
    fy = [r[1] for r in rows]
    corr = _pearson(_rankdata(fx), _rankdata(fy))
    if corr is None:
        return None
    return float(round(corr, 6))


def summarize_factor_ic(
    observations: Sequence[dict[str, Any]],
    *,
    factor_key: str = "factor",
    return_key: str = "forward_return",
) -> dict[str, Any]:
    """Aggregate mean |IC| and hit-rate of positive IC across dated cross-sections.

    Each observation: ``{asof, values: [{factor, forward_return}, ...]}``
    or flat rows with shared ``asof``.
    """
    by_asof: dict[str, list[dict[str, Any]]] = {}
    for row in observations:
        if not isinstance(row, dict):
            continue
        if "values" in row:
            asof = str(row.get("asof") or "")
            vals = row.get("values") or []
            if not asof or not isinstance(vals, list):
                continue
            by_asof.setdefault(asof, []).extend(
                v for v in vals if isinstance(v, dict)
            )
            continue
        asof = str(row.get("asof") or "")
        if not asof:
            continue
        by_asof.setdefault(asof, []).append(row)

    ics: list[dict[str, Any]] = []
    for asof, vals in sorted(by_asof.items()):
        factors = [v.get(factor_key) for v in vals]
        fwds = [v.get(return_key) for v in vals]
        ic = spearman_rank_ic(factors, fwds)
        if ic is None:
            continue
        ics.append({"asof": asof, "ic": ic, "n": len(vals)})

    if not ics:
        return {
            "ok": True,
            "n_dates": 0,
            "mean_ic": None,
            "mean_abs_ic": None,
            "positive_ic_rate": None,
            "dates": [],
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "note": "无足够截面计算 IC；不进 brief 主路径。",
        }

    ic_vals = [d["ic"] for d in ics]
    mean_ic = round(sum(ic_vals) / len(ic_vals), 6)
    mean_abs = round(sum(abs(x) for x in ic_vals) / len(ic_vals), 6)
    pos_rate = round(sum(1 for x in ic_vals if x > 0) / len(ic_vals), 4)
    return {
        "ok": True,
        "n_dates": len(ics),
        "mean_ic": mean_ic,
        "mean_abs_ic": mean_abs,
        "positive_ic_rate": pos_rate,
        "dates": ics,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": "Rank IC 摘要（M-R4）；数据由调用方注入；非投资建议。",
        "disclaimer": "Research only; not investment advice.",
    }
