"""Cross-sectional rank IC helper (M-R4 thin + deep slice) + S2 admission gate.

Pure in-memory Spearman IC (no scipy); no HTTP / no dual pipeline.
Not on the daily brief / lvrev path.

``S2`` adds :func:`admit_factor` / :func:`build_factor_ic_report`: the IC/ICIR
gate that decides which library factors (see :mod:`factors`) are **启用**.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


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
            "std_ic": None,
            "icir": None,
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
    std_ic = None
    icir = None
    if len(ic_vals) >= 2:
        mu = sum(ic_vals) / len(ic_vals)
        var = sum((x - mu) ** 2 for x in ic_vals) / (len(ic_vals) - 1)
        std_ic = round(var**0.5, 6)
        if std_ic > 0:
            icir = round(mu / std_ic, 6)
    return {
        "ok": True,
        "n_dates": len(ics),
        "mean_ic": mean_ic,
        "mean_abs_ic": mean_abs,
        "std_ic": std_ic,
        "icir": icir,
        "positive_ic_rate": pos_rate,
        "dates": ics,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": "Rank IC / ICIR 摘要（M-R4）；数据由调用方注入；不进 lvrev 主路径；非投资建议。",
        "disclaimer": "Research only; not investment advice.",
    }


def summarize_factor_ic_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    asof_key: str = "asof",
    factor_key: str = "factor",
    return_key: str = "forward_return",
) -> dict[str, Any]:
    """Convenience: flat rows ``{asof, factor, forward_return}`` → ``summarize_factor_ic``.

    Deep-knife helper for Workbench / scripts; still off the daily brief path.
    """
    flat: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        asof = str(row.get(asof_key) or "")
        if not asof:
            continue
        flat.append(
            {
                "asof": asof,
                factor_key: row.get(factor_key),
                return_key: row.get(return_key),
            }
        )
    return summarize_factor_ic(flat, factor_key=factor_key, return_key=return_key)


# --------------------------------------------------------------------------- #
# S2 — factor admission gate (IC / ICIR) over a PIT feature frame
# --------------------------------------------------------------------------- #

#: Admission thresholds — a factor must clear **all** of them to count as
#: "启用". Chosen from common cross-sectional equity practice: |mean IC| >= 0.02,
#: |ICIR| >= 0.15, and at least 20 evaluated cross-sections.
DEFAULT_ADMISSION: dict[str, float] = {
    "min_abs_ic": 0.02,
    "min_abs_icir": 0.15,
    "min_dates": 20,
}

#: Orthogonality ceiling: a factor whose |Spearman ρ| against an already-enabled
#: factor reaches this is **redundant** and is not enabled (acceptance: 正交因子).
DEFAULT_MAX_CORR = 0.7


def _thresholds(overrides: Mapping[str, Any] | None) -> dict[str, float]:
    th: dict[str, float] = dict(DEFAULT_ADMISSION)
    if not overrides:
        return th
    for key, value in overrides.items():
        if value is None:
            continue
        try:
            th[key] = float(value)
        except (TypeError, ValueError):
            continue
    return th


def admit_factor(
    summary: Mapping[str, Any],
    *,
    direction: int = 1,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the IC / ICIR admission gate to one ``summarize_factor_ic`` block.

    Returns ``{passed, checks, reasons, direction, mean_ic, icir, n_dates,
    thresholds}``. A factor passes only when **every** check is true; failed
    checks are echoed (Chinese) in ``reasons`` so the report is self-explaining.
    Direction consistency is a hard gate: a factor whose realised IC sign
    contradicts its declared ``direction`` is never enabled.
    """
    th = _thresholds(thresholds)
    mean_ic = summary.get("mean_ic")
    icir = summary.get("icir")
    n_dates = int(summary.get("n_dates") or 0)

    checks: dict[str, bool] = {}
    reasons: list[str] = []

    min_dates = int(th["min_dates"])
    checks["n_dates"] = n_dates >= min_dates
    if not checks["n_dates"]:
        reasons.append(f"有效截面数 {n_dates} < {min_dates}")

    abs_ic = abs(float(mean_ic)) if mean_ic is not None else None
    checks["abs_ic"] = abs_ic is not None and abs_ic >= th["min_abs_ic"]
    if not checks["abs_ic"]:
        shown = "n/a" if abs_ic is None else f"{abs_ic:.4f}"
        reasons.append(f"|IC| {shown} < {th['min_abs_ic']:g}")

    abs_icir = abs(float(icir)) if icir is not None else None
    checks["abs_icir"] = abs_icir is not None and abs_icir >= th["min_abs_icir"]
    if not checks["abs_icir"]:
        shown = "n/a" if abs_icir is None else f"{abs_icir:.4f}"
        reasons.append(f"|ICIR| {shown} < {th['min_abs_icir']:g}")

    want = 1 if direction >= 0 else -1
    got = None if mean_ic is None else (1 if mean_ic >= 0 else -1)
    checks["sign"] = got is not None and got == want
    if not checks["sign"]:
        reasons.append(f"IC 方向与声明 ({'+' if want > 0 else '-'}) 不一致")

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "reasons": reasons,
        "direction": want,
        "mean_ic": mean_ic,
        "icir": icir,
        "n_dates": n_dates,
        "thresholds": th,
    }


def select_enabled(
    order: Sequence[str],
    passed: Mapping[str, bool],
    correlation: Any = None,
    *,
    max_corr: float = DEFAULT_MAX_CORR,
) -> dict[str, Any]:
    """Greedy **orthogonal** admission over an ordered factor list.

    Walks ``order`` (incumbents first, then strongest-first) and keeps a factor
    only if it clears IC/ICIR (``passed``) **and** its ``|Spearman rho|`` against
    every already-kept factor stays below ``max_corr``. Pure and dependency-free
    so the rule can be unit-tested without any market data.

    Returns ``{"enabled", "redundant", "rejected", "redundancy"}`` where
    ``redundancy[name] = (kept_name, rho)``.
    """
    enabled: list[str] = []
    redundant: list[str] = []
    rejected: list[str] = []
    redundancy: dict[str, tuple[str, float]] = {}

    for name in order:
        if not passed.get(name, False):
            rejected.append(name)
            continue
        worst_name: str | None = None
        worst = 0.0
        if correlation is not None:
            for kept in enabled:
                try:
                    value = float(correlation.loc[name, kept])
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                if value != value:  # NaN
                    continue
                if abs(value) > abs(worst):
                    worst, worst_name = value, kept
        if worst_name is not None and abs(worst) >= float(max_corr):
            redundant.append(name)
            redundancy[name] = (worst_name, worst)
        else:
            enabled.append(name)

    return {
        "enabled": enabled,
        "redundant": redundant,
        "rejected": rejected,
        "redundancy": redundancy,
    }


def build_factor_ic_report(
    feats: Any,
    *,
    horizon: int = 20,
    factors: Sequence[str] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    sample_every: int = 5,
    min_names: int = 30,
    max_corr: float = DEFAULT_MAX_CORR,
    compute_correlation: bool = True,
) -> dict[str, Any]:
    """Run the whole factor library through the IC/ICIR + orthogonality gate.

    ``feats`` is a PIT feature frame (see :func:`factors.build_feature_frame`)
    with ``code`` / ``trade_date`` / ``close``. For every sampled cross-section
    the forward return ``close.shift(-horizon) / close - 1`` (per code) is
    correlated with each library factor via :func:`summarize_factor_ic` — the
    single IC point — then gated by :func:`admit_factor`.

    A second, **orthogonality** pass then keeps incumbents first (library
    ``BASELINE_FACTORS``) and walks the new factors by ``|ICIR|`` descending:
    a factor that clears IC/ICIR but correlates with an already-enabled one at
    ``|rho| >= max_corr`` is marked **redundant**, not enabled.

    ``sample_every`` sub-samples trading days so overlapping forward windows do
    not dominate; ``min_names`` drops degenerate cross-sections. The report is
    **off** the brief / picks path and never mutates the frame.
    """
    from .factors import BASELINE_FACTORS, FACTOR_LIBRARY, build_factor_frame, factor_correlation

    names: list[str] = list(factors) if factors is not None else list(FACTOR_LIBRARY)
    unknown = [n for n in names if n not in FACTOR_LIBRARY]
    if unknown:
        return _failed_report(f"未知因子：{unknown}；已知={list(FACTOR_LIBRARY)}", names=names)
    if not names:
        return _failed_report("因子列表为空。", names=names)

    need = {"code", "trade_date", "close"}
    missing = sorted(need - set(getattr(feats, "columns", [])))
    if missing:
        return _failed_report(f"特征帧缺列：{missing}", names=names)
    if len(feats) == 0:
        return _failed_report("空特征帧；不进主路径。", names=names)

    frame = build_factor_frame(feats, factors=names)
    closes = feats.groupby("code", sort=False)["close"]
    fwd = closes.shift(-int(horizon)) / feats["close"].astype(float) - 1.0

    work = frame.copy()
    work["_fwd"] = fwd.to_numpy()
    work["_date"] = feats["trade_date"].to_numpy()
    by_date = {key: sub for key, sub in work.groupby("_date", sort=True)}

    dates = sorted(by_date)
    step = max(1, int(sample_every))
    sampled = dates[::step]

    observations: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    evaluated = 0
    for day in sampled:
        sub = by_date.get(day)
        if sub is None:
            continue
        realised = sub["_fwd"]
        valid = realised.notna()
        if int(valid.sum()) < int(min_names):
            continue
        evaluated += 1
        asof = _asof_label(day)
        for name in names:
            values = sub[name]
            mask = values.notna() & valid
            if int(mask.sum()) < int(min_names):
                continue
            rows = [
                {"factor": float(f), "forward_return": float(r)}
                for f, r in zip(values[mask].to_numpy(), realised[mask].to_numpy(), strict=True)
            ]
            observations[name].append({"asof": asof, "values": rows})

    if evaluated == 0:
        return _failed_report(
            f"无可评估截面（min_names={min_names} 太严或样本不足）。", names=names
        )

    report: dict[str, Any] = {}
    for name in names:
        spec = FACTOR_LIBRARY[name]
        summary = summarize_factor_ic(observations[name])
        report[name] = {
            "label": spec.label,
            "direction": spec.direction,
            "description": spec.description,
            "n_dates": summary.get("n_dates"),
            "mean_ic": summary.get("mean_ic"),
            "mean_abs_ic": summary.get("mean_abs_ic"),
            "std_ic": summary.get("std_ic"),
            "icir": summary.get("icir"),
            "positive_ic_rate": summary.get("positive_ic_rate"),
            "admission": admit_factor(summary, direction=spec.direction, thresholds=thresholds),
        }

    corr = None
    corr_block = None
    if compute_correlation and len(names) >= 2:
        subset = work.loc[work["_date"].isin(set(sampled)), names]
        corr = factor_correlation(subset)
        corr_block = {
            str(a): {
                str(b): (None if corr.loc[a, b] != corr.loc[a, b] else round(float(corr.loc[a, b]), 4))
                for b in corr.columns
            }
            for a in corr.index
        }

    def _strength(name: str) -> float:
        icir = report[name]["icir"]
        if icir is not None:
            return abs(float(icir))
        ic = report[name]["mean_ic"]
        return abs(float(ic)) if ic is not None else -1.0

    # incumbents first, then new factors strongest-first
    order: list[str] = [n for n in BASELINE_FACTORS if n in names]
    order += sorted([n for n in names if n not in order], key=_strength, reverse=True)

    passed = {n: report[n]["admission"]["passed"] for n in names}
    selection = select_enabled(order, passed, corr, max_corr=max_corr)

    for name, (kept, rho) in selection["redundancy"].items():
        admission = report[name]["admission"]
        admission["checks"]["orthogonal"] = False
        admission["reasons"].append(
            f"与已启用因子 {kept} 相关 {rho:+.3f}，|rho| >= {float(max_corr):g}（冗余）"
        )
        admission["passed"] = False

    enabled = selection["enabled"]
    redundant = selection["redundant"]
    rejected = selection["rejected"]

    return {
        "ok": True,
        "horizon": int(horizon),
        "sampleEvery": step,
        "minNames": int(min_names),
        "maxCorr": float(max_corr),
        "nDates": evaluated,
        "factors": report,
        "correlation": corr_block,
        "enabled": enabled,
        "redundant": redundant,
        "rejected": rejected,
        "disabled": rejected + redundant,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": "因子 IC/ICIR + 正交准入（S2）；SIMULATE；**不达标不启用**；不进 picks 主路径；非投资建议。",
        "disclaimer": "Research only; not investment advice.",
    }


def _asof_label(day: Any) -> str:
    """ISO ``YYYY-MM-DD`` label without importing pandas into this pure module."""
    text = str(day)
    return text[:10] if len(text) >= 10 else text


def _failed_report(reason: str, *, names: Sequence[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "horizon": None,
        "sampleEvery": None,
        "minNames": None,
        "maxCorr": None,
        "nDates": 0,
        "factors": {},
        "correlation": None,
        "requested": list(names),
        "enabled": [],
        "redundant": [],
        "rejected": [],
        "disabled": [],
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": "因子 IC/ICIR + 正交准入（S2）；fail-closed。",
        "disclaimer": "Research only; not investment advice.",
    }
