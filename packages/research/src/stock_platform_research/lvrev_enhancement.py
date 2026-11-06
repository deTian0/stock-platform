"""lvrev enhancement experiments (docs/plans/lvrev-enhancement.md).

Three opt-in treatments, each compared alone against the factory lvrev baseline
through the **same** :func:`book_replay.replay_book` engine:

1. ``r2`` — Round2 Set A hard gates as a second-pass filter on lvrev candidates
2. ``regime`` — ``s1_regime_state`` weak/unknown days block *new* entries only
3. exit variants — ``tiered_stop`` / ``trail_tp`` / ``time_stop`` (ExitPolicy flags)

Factory defaults stay off: no knobs → bit-identical to
:func:`neutralization_ab.run_neutralization_book` raw arm. SIMULATE only.
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
from .gates import EntryGateParams, apply_entry_gates
from .lvrev import score_lvrev
from .neutralization import NeutralizeParams
from .portfolio import compute_metrics, norm_code
from .rules import (
    DEFAULT_TIME_STOP_DAYS,
    ExitPolicy,
)
from .shadow_board.backtest import frame_to_universe
from .shadow_board.round2 import apply_round2_set_a
from .shadow_board.schools import s1_regime_state
from .strategy_ab import AB_METRIC_KEYS, _delta_metrics, _review_block

#: Variant ids (N = 5). Parameters are frozen in the plan; no search.
VARIANTS: tuple[str, ...] = ("r2", "regime", "tiered_stop", "trail_tp", "time_stop")
BASELINE = "baseline"

#: Weak / unknown → no new entries (plan §1 ``regime``).
_REGIME_BLOCK = frozenset({"weak", "unknown"})


def lvrev_round2_entry_provider(
    *,
    round2_filter: bool = False,
    name_map: Mapping[str, str] | None = None,
    reversal_q: float | None = None,
    min_pick_score: float = 0.80,
    value_factor: bool = False,
    weights: Mapping[str, float] | None = None,
    gate_params: EntryGateParams | None = None,
    neutralize: NeutralizeParams | None = None,
    max_per_industry: int | None = None,
) -> EntryProvider:
    """lvrev TopN, optionally filtered by Round2 Set A (school ``S0``).

    ``round2_filter=False`` (default) returns the factory
    :func:`screener_entry_provider` — same callable behaviour as today.
    """
    if not round2_filter:
        return screener_entry_provider(
            reversal_q=reversal_q,
            min_pick_score=min_pick_score,
            value_factor=value_factor,
            weights=weights,
            gate_params=gate_params,
            neutralize=neutralize,
            max_per_industry=max_per_industry,
        )

    if gate_params is None:
        gate_params = EntryGateParams(
            reversal_q=0.30 if reversal_q is None else float(reversal_q)
        )
    elif reversal_q is not None:
        gate_params = replace(gate_params, reversal_q=float(reversal_q))

    names = {norm_code(k): str(v) for k, v in (name_map or {}).items() if v}

    def _provider(ctx: EntryContext) -> list[dict[str, Any]]:
        scored = score_lvrev(
            ctx.frame,
            value_factor=value_factor,
            weights=weights,
            neutralize=neutralize,
        )
        mask = apply_entry_gates(scored, params=gate_params)
        elig = scored.loc[mask]
        elig = elig[elig["composite_score"] >= min_pick_score]
        if elig.empty:
            return []
        if max_per_industry is not None:
            ind_col = neutralize.industry_col if neutralize is not None else "industry"
            if ind_col in elig.columns and int(max_per_industry) > 0:
                elig = (
                    elig.groupby(ind_col, sort=False)
                    .head(int(max_per_industry))
                    .sort_values("composite_score", ascending=False)
                )
                if elig.empty:
                    return []

        cands: list[dict[str, Any]] = []
        # Map Round2's norm_code back to the frame's raw code so replay_book's
        # px_by_code lookup (keyed by frame ``code``) can exit the position.
        by_norm: dict[str, dict[str, Any]] = {}
        for _, row in elig.iterrows():
            raw = str(row["code"])
            code = norm_code(raw)
            amount = row["amount"] if "amount" in elig.columns else None
            industry = row["industry"] if "industry" in elig.columns else None
            if industry is not None and str(industry) == "_unknown":
                industry = None
            cands.append(
                {
                    "code": code,
                    "name": names.get(code, ""),
                    "school": "S0",
                    "schoolName": "lvrev",
                    "score": float(row["composite_score"]),
                    "amount": None if amount is None or (isinstance(amount, float) and amount != amount) else amount,
                    "pct_chg": row.get("pct_chg"),
                    "industry": None if industry is None else str(industry),
                }
            )
            by_norm[code] = {
                "code": raw,  # frame key — required for exit price lookups
                "close": float(row["close"]),
                "pct_chg": row.get("pct_chg"),
            }

        board = apply_round2_set_a({"S0": {"candidates": cands}})
        out: list[dict[str, Any]] = []
        for row in board.get("passed") or []:
            hit = by_norm.get(norm_code(row.get("code")))
            if hit is not None:
                out.append(hit)
        return out

    return _provider


def build_lvrev_regime_map(
    feats: pd.DataFrame,
    *,
    name_map: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    """``YYYY-MM-DD → may_open_new`` from :func:`s1_regime_state`.

    ``weak`` / ``unknown`` → ``False`` (no new entries); ``strong`` / ``mid`` →
    ``True``. Existing positions are unaffected (:class:`ReplayParams.regime`).
    """
    out: dict[str, bool] = {}
    if feats is None or feats.empty:
        return out
    for day, frame in feats.groupby("trade_date", sort=True):
        day_str = pd.Timestamp(day).date().isoformat()
        universe = frame_to_universe(frame, name_map=name_map)
        state = str(s1_regime_state(universe).get("state") or "unknown")
        out[day_str] = state not in _REGIME_BLOCK
    return out


def exit_policy_for_variant(variant: str) -> ExitPolicy:
    """Factory ExitPolicy, or one experimental flag for the named exit variant."""
    if variant == "tiered_stop":
        return ExitPolicy(tiered_stop=True)
    if variant == "trail_tp":
        return ExitPolicy(trail_tp=True)
    if variant == "time_stop":
        return ExitPolicy(time_stop_days=DEFAULT_TIME_STOP_DAYS)
    if variant in (BASELINE, "r2", "regime"):
        return ExitPolicy()
    raise ValueError(f"unknown variant: {variant!r}")


def run_lvrev_variant(
    feats: pd.DataFrame,
    *,
    variant: str = BASELINE,
    params: ReplayParams | None = None,
    name_map: Mapping[str, str] | None = None,
    min_pick_score: float = 0.80,
    weights: Mapping[str, float] | None = None,
    gate_params: Any = None,
    value_factor: bool = False,
    reversal_q: float | None = None,
    regime_map: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Replay one lvrev enhancement variant through the shared book engine."""
    variant = str(variant or BASELINE).strip().lower()
    if variant not in (BASELINE, *VARIANTS):
        raise ValueError(f"variant must be baseline or one of {VARIANTS}, got {variant!r}")

    base_params = params or ReplayParams()
    exit_policy = exit_policy_for_variant(variant)
    regime: Mapping[str, bool] | None = None
    if variant == "regime":
        regime = regime_map if regime_map is not None else build_lvrev_regime_map(
            feats, name_map=name_map
        )
    run_params = replace(base_params, exit_policy=exit_policy, regime=regime)

    provider = lvrev_round2_entry_provider(
        round2_filter=(variant == "r2"),
        name_map=name_map,
        reversal_q=reversal_q,
        min_pick_score=min_pick_score,
        value_factor=value_factor,
        weights=weights,
        gate_params=gate_params,
    )
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


def year_slice_metrics(
    equity_curve: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    *,
    initial_capital: float,
    years: Sequence[int] | None = None,
) -> dict[str, dict[str, Any]]:
    """Slice one full-span replay by calendar year (plan §3 / final-board §11.7).

    No cold start per year: year return = year-end equity / prior year-end
    equity − 1 (2021 denominator = ``initial_capital``). Intra-year Sharpe /
    MDD use daily returns with the first day relative to prior year-end equity.
    Closed trades attributed by ``exit_date`` year.
    """
    curve = list(equity_curve or [])
    if not curve:
        return {}
    by_year: dict[int, list[dict[str, Any]]] = {}
    for pt in curve:
        y = int(str(pt.get("date") or "")[:4])
        by_year.setdefault(y, []).append(dict(pt))
    year_list = list(years) if years is not None else sorted(by_year)
    trades_by_year: dict[int, list[dict[str, Any]]] = {y: [] for y in year_list}
    for t in trades or []:
        ed = str(t.get("exit_date") or "")
        if len(ed) >= 4:
            y = int(ed[:4])
            if y in trades_by_year:
                trades_by_year[y].append(dict(t))

    out: dict[str, dict[str, Any]] = {}
    prev_equity = float(initial_capital)
    for y in year_list:
        pts = by_year.get(y) or []
        if not pts:
            out[str(y)] = {
                "n_days": 0,
                "total_return": None,
                "max_drawdown": None,
                "sharpe": None,
                "win_rate": None,
                "n_trades": 0,
                "prior_equity": prev_equity,
                "final_equity": prev_equity,
            }
            continue
        synthetic = [{"date": f"{y}-00-00", "equity": prev_equity}, *pts]
        year_trades = trades_by_year.get(y) or []
        m = compute_metrics(synthetic, year_trades, initial_capital=prev_equity)
        final_eq = float(pts[-1]["equity"])
        n_real = len(pts)
        years_frac = n_real / 252.0
        m["n_days"] = n_real
        m["turnover_per_year"] = (
            round(len(year_trades) / years_frac, 1) if years_frac > 0 else 0.0
        )
        m["prior_equity"] = round(prev_equity, 2)
        out[str(y)] = m
        prev_equity = final_eq
    return out


def _pass_windows(decision: Mapping[str, Any]) -> int:
    return sum(
        1
        for w in decision.get("windows") or []
        if str(w.get("verdict") or "") == "pass"
    )


def evaluate_criteria(
    *,
    baseline_arm: Mapping[str, Any],
    variant_arm: Mapping[str, Any],
    baseline_years: Mapping[str, Mapping[str, Any]],
    variant_years: Mapping[str, Mapping[str, Any]],
    y1_baseline_pass: int,
    y1_variant_pass: int,
    y1_detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the four pre-registered pass criteria (plan §2). Any fail ⇒ fail."""
    years = sorted(set(baseline_years) & set(variant_years), key=int)
    sharpe_wins = 0
    year_rows: list[dict[str, Any]] = []
    excesses: list[float] = []
    for y in years:
        b = baseline_years[y]
        v = variant_years[y]
        b_s = b.get("sharpe")
        v_s = v.get("sharpe")
        b_ret = b.get("total_return")
        v_ret = v.get("total_return")
        ge = (
            b_s is not None
            and v_s is not None
            and float(v_s) >= float(b_s)
        )
        if ge:
            sharpe_wins += 1
        ex = (
            float(v_ret) - float(b_ret)
            if b_ret is not None and v_ret is not None
            else 0.0
        )
        excesses.append(ex)
        year_rows.append(
            {
                "year": int(y),
                "baseline": {
                    "total_return": b_ret,
                    "max_drawdown": b.get("max_drawdown"),
                    "sharpe": b_s,
                    "win_rate": b.get("win_rate"),
                    "n_trades": b.get("n_trades"),
                    "n_days": b.get("n_days"),
                },
                "variant": {
                    "total_return": v_ret,
                    "max_drawdown": v.get("max_drawdown"),
                    "sharpe": v_s,
                    "win_rate": v.get("win_rate"),
                    "n_trades": v.get("n_trades"),
                    "n_days": v.get("n_days"),
                },
                "sharpe_ge_baseline": ge,
                "excess_return": ex,
            }
        )

    a_ok = sharpe_wins >= 4
    total_ex = sum(excesses)
    max_contrib = None
    max_contrib_year = None
    if total_ex <= 0:
        b_ok = False
        b_reason = "六年超额之和 ≤ 0"
    else:
        contribs = [e / total_ex for e in excesses]
        max_i = max(range(len(contribs)), key=lambda i: contribs[i])
        max_contrib = contribs[max_i]
        max_contrib_year = int(years[max_i])
        b_ok = max_contrib <= 0.60
        b_reason = None if b_ok else f"{max_contrib_year} 单年贡献 {max_contrib:.1%} > 60%"
        for row, c in zip(year_rows, contribs):
            row["excess_contribution"] = c

    c_ok = int(y1_variant_pass) >= int(y1_baseline_pass)
    b_mdd = (baseline_arm.get("metrics") or {}).get("max_drawdown")
    v_mdd = (variant_arm.get("metrics") or {}).get("max_drawdown")
    d_ok = (
        b_mdd is not None
        and v_mdd is not None
        and float(v_mdd) >= float(b_mdd)
    )

    passed = bool(a_ok and b_ok and c_ok and d_ok)
    return {
        "passed": passed,
        "a": {
            "ok": a_ok,
            "sharpe_wins": sharpe_wins,
            "needed": 4,
            "years": len(years),
        },
        "b": {
            "ok": b_ok,
            "total_excess": total_ex,
            "max_contribution": max_contrib,
            "max_contribution_year": max_contrib_year,
            "reason": b_reason,
        },
        "c": {
            "ok": c_ok,
            "baseline_pass_windows": int(y1_baseline_pass),
            "variant_pass_windows": int(y1_variant_pass),
            "detail": y1_detail,
        },
        "d": {
            "ok": d_ok,
            "baseline_max_drawdown": b_mdd,
            "variant_max_drawdown": v_mdd,
        },
        "by_year": year_rows,
    }


def compare_lvrev_enhancements(
    feats: pd.DataFrame,
    *,
    variants: Sequence[str] = VARIANTS,
    params: ReplayParams | None = None,
    name_map: Mapping[str, str] | None = None,
    run_y1: bool = True,
) -> dict[str, Any]:
    """Run baseline + each variant; attach year slices, criteria, optional Y1."""
    from .adoption_gate import (
        AdoptionRule,
        CandidateSpec,
        build_windows,
        decide_adoption,
        run_candidate,
        slice_window,
    )

    params = params or ReplayParams()
    regime_map = build_lvrev_regime_map(feats, name_map=name_map)

    arms: dict[str, dict[str, Any]] = {}
    arms[BASELINE] = run_lvrev_variant(
        feats, variant=BASELINE, params=params, name_map=name_map
    )
    for vid in variants:
        arms[vid] = run_lvrev_variant(
            feats,
            variant=vid,
            params=params,
            name_map=name_map,
            regime_map=regime_map if vid == "regime" else None,
        )

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
        # Baseline self-compare (plan §3 note: AdoptionRule margin ⇒ 0/3 by construction)
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
            # CandidateSpec/run_candidate only know neutralize knobs — drive via run_lvrev_variant
            rows: list[dict[str, Any]] = []
            for w in windows:
                wf = slice_window(feats, w["start"], w["end"])
                b = run_candidate(wf, base_spec, params=params)
                v = run_lvrev_variant(
                    wf,
                    variant=vid,
                    params=params,
                    name_map=name_map,
                    regime_map=(
                        build_lvrev_regime_map(wf, name_map=name_map)
                        if vid == "regime"
                        else None
                    ),
                )
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
        b_m = arms[BASELINE]["metrics"]
        v_m = arms[vid]["metrics"]
        comparisons[vid] = {
            "metrics": v_m,
            "delta": _delta_metrics(b_m, v_m),
            "criteria": criteria,
            "by_year": criteria["by_year"],
            "review": arms[vid]["review"],
        }

    return {
        "ok": True,
        "nVariants": len(variants),
        "variants": list(variants),
        "baseline": {
            "metrics": arms[BASELINE]["metrics"],
            "review": arms[BASELINE]["review"],
            "by_year": year_slice_metrics(
                arms[BASELINE]["equity_curve"],
                arms[BASELINE]["trades"],
                initial_capital=params.initial_capital,
                years=[int(y) for y in year_keys],
            ),
            "y1_pass_windows": y1_pass.get(BASELINE, 0),
        },
        "comparisons": comparisons,
        "y1": y1_block,
        "arms": {
            k: {
                "metrics": v["metrics"],
                "final_equity": v["final_equity"],
                "n_days": v["n_days"],
                "tradeCount": len(v.get("trades") or []),
                "equity_curve": v["equity_curve"],
                "trades": v["trades"],
            }
            for k, v in arms.items()
        },
        "metricKeys": list(AB_METRIC_KEYS),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice. Excess vs index unavailable when market.db has no index rows.",
        "excessAvailable": False,
        "excessReason": "market.db 无指数行；超额按 fail-closed 标不可用",
    }


__all__ = [
    "BASELINE",
    "VARIANTS",
    "build_lvrev_regime_map",
    "compare_lvrev_enhancements",
    "evaluate_criteria",
    "exit_policy_for_variant",
    "lvrev_round2_entry_provider",
    "run_lvrev_variant",
    "year_slice_metrics",
]
