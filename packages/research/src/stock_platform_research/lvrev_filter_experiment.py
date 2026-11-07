"""lvrev entry-filter / cooldown experiments (docs/plans/lvrev-entry-filter.md).

Three opt-in treatments vs factory lvrev; defaults off → bit-identical baseline.
Reuses :func:`lvrev_enhancement.evaluate_criteria` (same four gates). SIMULATE only.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

import pandas as pd

from .book_replay import (
    EntryContext,
    EntryProvider,
    ReplayParams,
    replay_book,
    screener_entry_provider,
)
from .lvrev_enhancement import (
    BASELINE,
    evaluate_criteria,
    year_slice_metrics,
)
from .portfolio import compute_metrics
from .rules import CooldownPolicy
from .strategy_ab import _delta_metrics, _review_block

#: Frozen plan parameters — do not search.
NEAR_LIMIT_PCT = 7.0
AMOUNT_FLOOR = 50_000_000.0
COOLDOWN_DAYS = 5

VARIANTS: tuple[str, ...] = ("near_limit7", "amount50m", "cooldown5")


def filtered_entry_provider(
    *,
    near_limit_pct: float | None = None,
    amount_min: float | None = None,
) -> EntryProvider:
    """Factory screener, then optional near-limit / amount floors.

    ``near_limit_pct`` / ``amount_min`` both ``None`` → identical to
    :func:`screener_entry_provider` (callable still wraps for a stable object).
    """
    base = screener_entry_provider()
    if near_limit_pct is None and amount_min is None:
        return base

    lim = None if near_limit_pct is None else float(near_limit_pct)
    floor = None if amount_min is None else float(amount_min)

    def _provider(ctx: EntryContext) -> list[dict[str, Any]]:
        rows = list(base(ctx))
        amount_by: dict[str, Any] = {}
        if floor is not None and "amount" in ctx.frame.columns:
            amount_by = {
                str(c): a
                for c, a in zip(ctx.frame["code"], ctx.frame["amount"])
            }
        out: list[dict[str, Any]] = []
        for row in rows:
            if lim is not None:
                pct = row.get("pct_chg")
                try:
                    if pct is not None and float(pct) == float(pct) and float(pct) >= lim:
                        continue
                except (TypeError, ValueError):
                    pass  # missing / bad pct → keep (plan: 缺列放行)
            if floor is not None:
                code = str(row.get("code"))
                amt = amount_by.get(code)
                try:
                    if amt is None or float(amt) != float(amt) or float(amt) < floor:
                        continue
                except (TypeError, ValueError):
                    continue
            out.append(row)
        return out

    return _provider


def run_filter_variant(
    feats: pd.DataFrame,
    *,
    variant: str = BASELINE,
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """Replay one filter / cooldown variant through the shared book engine."""
    variant = str(variant or BASELINE).strip().lower()
    if variant not in (BASELINE, *VARIANTS):
        raise ValueError(f"variant must be baseline or one of {VARIANTS}, got {variant!r}")

    base_params = params or ReplayParams()
    near = NEAR_LIMIT_PCT if variant == "near_limit7" else None
    amt = AMOUNT_FLOOR if variant == "amount50m" else None
    cooldown = (
        CooldownPolicy(cooldown_days=COOLDOWN_DAYS)
        if variant == "cooldown5"
        else base_params.cooldown_policy
    )
    run_params = replace(base_params, cooldown_policy=cooldown)
    provider = filtered_entry_provider(near_limit_pct=near, amount_min=amt)
    loop = replay_book(feats, entry_provider=provider, params=run_params)
    initial = run_params.initial_capital
    return {
        "ok": True,
        "variant": variant,
        "equity_curve": loop["equity_curve"],
        "trades": loop["trades"],
        "open_positions": loop.get("open_positions") or [],
        "n_days": loop["n_days"],
        "final_equity": loop["final_equity"],
        "initial_capital": loop["initial_capital"],
        "metrics": compute_metrics(
            loop["equity_curve"], loop["trades"], initial_capital=initial
        ),
        "review": _review_block(loop["trades"], loop.get("open_positions")),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


def compare_lvrev_filters(
    feats: pd.DataFrame,
    *,
    variants: Sequence[str] = VARIANTS,
    params: ReplayParams | None = None,
    run_y1: bool = True,
    index_close: Mapping[str, float] | None = None,
    benchmark: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Baseline + each filter variant; same criteria block as lvrev-enhancement."""
    from .adoption_gate import (
        AdoptionRule,
        CandidateSpec,
        build_windows,
        decide_adoption,
        run_candidate,
        slice_window,
    )
    from .lvrev_enhancement import _pass_windows

    params = params or ReplayParams()
    arms: dict[str, dict[str, Any]] = {
        BASELINE: run_filter_variant(feats, variant=BASELINE, params=params)
    }
    for vid in variants:
        arms[vid] = run_filter_variant(feats, variant=vid, params=params)

    years = year_slice_metrics(
        arms[BASELINE]["equity_curve"],
        arms[BASELINE]["trades"],
        initial_capital=params.initial_capital,
    )
    year_keys = tuple(sorted(years, key=int))

    y1_block: dict[str, Any] | None = None
    y1_pass: dict[str, int] = {BASELINE: 0}
    if run_y1 and not feats.empty:
        last = pd.Timestamp(feats["trade_date"].max()).date()
        windows = build_windows(last, years=1, count=3)
        base_spec = CandidateSpec(name="lvrev", label="lvrev 基线")
        per_window_base: list[dict[str, Any]] = []
        for w in windows:
            wf = slice_window(feats, w["start"], w["end"])
            b = run_candidate(wf, base_spec, params=params)
            per_window_base.append(
                {
                    "window": w["label"],
                    "start": w["start"],
                    "end": w["end"],
                    "baseline": b["metrics"],
                    "candidate": b["metrics"],
                }
            )
        base_decision = decide_adoption(per_window_base, AdoptionRule())
        y1_pass[BASELINE] = _pass_windows(base_decision)
        y1_block = {
            "windows": [
                {"label": w["label"], "start": w["start"], "end": w["end"]}
                for w in windows
            ],
            "baseline": base_decision,
            "variants": {},
        }
        for vid in variants:
            rows: list[dict[str, Any]] = []
            for w in windows:
                wf = slice_window(feats, w["start"], w["end"])
                b = run_candidate(wf, base_spec, params=params)
                v = run_filter_variant(wf, variant=vid, params=params)
                rows.append(
                    {
                        "window": w["label"],
                        "start": w["start"],
                        "end": w["end"],
                        "baseline": b["metrics"],
                        "candidate": v["metrics"],
                    }
                )
            decision = decide_adoption(rows, AdoptionRule())
            y1_pass[vid] = _pass_windows(decision)
            y1_block["variants"][vid] = decision

    comparisons: dict[str, Any] = {}
    for vid in variants:
        v_years = year_slice_metrics(
            arms[vid]["equity_curve"],
            arms[vid]["trades"],
            initial_capital=params.initial_capital,
            years=[int(y) for y in year_keys],
        )
        b_years = year_slice_metrics(
            arms[BASELINE]["equity_curve"],
            arms[BASELINE]["trades"],
            initial_capital=params.initial_capital,
            years=[int(y) for y in year_keys],
        )
        criteria = evaluate_criteria(
            baseline_arm=arms[BASELINE],
            variant_arm=arms[vid],
            baseline_years=b_years,
            variant_years=v_years,
            y1_baseline_pass=y1_pass.get(BASELINE, 0),
            y1_variant_pass=y1_pass.get(vid, 0),
            y1_detail=(y1_block or {}).get("variants", {}).get(vid) if y1_block else None,
        )
        comparisons[vid] = {
            "metrics": arms[vid]["metrics"],
            "delta": _delta_metrics(arms[BASELINE]["metrics"], arms[vid]["metrics"]),
            "criteria": criteria,
            "by_year": criteria["by_year"],
            "review": arms[vid]["review"],
        }

    out: dict[str, Any] = {
        "ok": True,
        "nVariants": len(variants),
        "variants": list(variants),
        "plan": "docs/plans/lvrev-entry-filter.md",
        "parameters": {
            "near_limit_pct": NEAR_LIMIT_PCT,
            "amount_floor": AMOUNT_FLOOR,
            "cooldown_days": COOLDOWN_DAYS,
        },
        "baseline": {
            "metrics": arms[BASELINE]["metrics"],
            "review": arms[BASELINE]["review"],
        },
        "comparisons": comparisons,
        "y1": y1_block,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }
    if index_close is not None or benchmark is not None:
        out["benchmark"] = benchmark
        out["indexClosePoints"] = len(index_close or {})
    return out


__all__ = [
    "AMOUNT_FLOOR",
    "COOLDOWN_DAYS",
    "NEAR_LIMIT_PCT",
    "VARIANTS",
    "compare_lvrev_filters",
    "filtered_entry_provider",
    "run_filter_variant",
]
