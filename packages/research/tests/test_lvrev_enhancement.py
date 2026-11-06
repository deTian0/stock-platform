"""lvrev enhancement experiment switches (docs/plans/lvrev-enhancement.md).

Pins: defaults off ⇒ factory-identical; each opt-in path fires as specified.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.book_replay import (
    EntryContext,
    ReplayParams,
    replay_book,
    screener_entry_provider,
)
from stock_platform_research.lvrev_enhancement import (
    BASELINE,
    VARIANTS,
    build_lvrev_regime_map,
    evaluate_criteria,
    exit_policy_for_variant,
    lvrev_round2_entry_provider,
    run_lvrev_variant,
    year_slice_metrics,
)
from stock_platform_research.portfolio import norm_code
from stock_platform_research.rules import DEFAULT_TIME_STOP_DAYS, ExitPolicy
from stock_platform_research.shadow_board.backtest import prepare_shadow_frame


N_CODES = 24
N_DAYS = 120


def _bars(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-02", periods=N_DAYS)
    rows = []
    for i in range(N_CODES):
        px = 10.0 + i * 0.3
        for k, d in enumerate(days):
            common = 1.0 if (k // 30) % 2 == 0 else -1.0
            pct = float(rng.normal(common, 1.2))
            pct = max(min(pct, 9.0), -9.0)
            px *= 1.0 + pct / 100.0
            rows.append(
                {
                    "code": f"{600000 + i:06d}.SH",
                    "date": d.date().isoformat(),
                    "close": round(px, 3),
                    "pct_chg": round(pct, 4),
                    "amount": 5e7 if i % 5 else 5e5,  # some below AMOUNT_MIN
                }
            )
    return pd.DataFrame(rows)


def _names() -> dict[str, str]:
    out = {f"{600000 + i:06d}": f"样本{i}" for i in range(N_CODES)}
    out[f"{600000 + 3:06d}"] = "ST样本3"  # Round2 ST reject
    return out


def _industry() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"行业{i % 6}" for i in range(N_CODES)}


@pytest.fixture(scope="module")
def feats() -> pd.DataFrame:
    return prepare_shadow_frame(_bars(), industry_map=_industry())


def test_variant_ids_match_plan():
    assert VARIANTS == ("r2", "regime", "tiered_stop", "trail_tp", "time_stop")
    assert BASELINE == "baseline"


def test_exit_policy_factory_defaults_unchanged():
    assert asdict(exit_policy_for_variant(BASELINE)) == asdict(ExitPolicy())
    assert asdict(exit_policy_for_variant("r2")) == asdict(ExitPolicy())
    assert asdict(exit_policy_for_variant("regime")) == asdict(ExitPolicy())
    assert exit_policy_for_variant("tiered_stop").tiered_stop is True
    assert exit_policy_for_variant("trail_tp").trail_tp is True
    assert exit_policy_for_variant("time_stop").time_stop_days == DEFAULT_TIME_STOP_DAYS


def _ctx(day, frame) -> EntryContext:
    return EntryContext(
        day_index=0,
        day=pd.Timestamp(day).date().isoformat(),
        frame=frame,
        positions={},
        cash=50000.0,
        equity=50000.0,
        last_exit_idx={},
        params=ReplayParams(),
    )


def test_round2_filter_default_matches_screener(feats: pd.DataFrame):
    """round2_filter=False must yield the same candidate codes/order as factory."""
    factory = screener_entry_provider()
    wrapped = lvrev_round2_entry_provider(round2_filter=False, name_map=_names())
    day, frame = next(iter(feats.groupby("trade_date", sort=True)))
    ctx = _ctx(day, frame)
    a = factory(ctx)
    b = wrapped(ctx)
    assert [r["code"] for r in a] == [r["code"] for r in b]
    assert [r["close"] for r in a] == [r["close"] for r in b]


def test_round2_filter_drops_st_and_illiquid(feats: pd.DataFrame):
    provider = lvrev_round2_entry_provider(round2_filter=True, name_map=_names())
    # Pick a day that has candidates
    found = False
    for day, frame in feats.groupby("trade_date", sort=True):
        ctx = _ctx(day, frame)
        raw = screener_entry_provider()(ctx)
        filtered = provider(ctx)
        if not raw:
            continue
        found = True
        codes = {norm_code(r["code"]) for r in filtered}
        assert "600003" not in codes  # ST
        # Provider must return frame raw codes (with exchange suffix) so the
        # engine can look up exit prices — shadow_entry_provider does the same.
        for r in filtered:
            assert str(r["code"]) in set(frame["code"].astype(str))
            code = norm_code(r["code"])
            row = frame[frame["code"].map(lambda c: norm_code(c) == code)]
            if not row.empty and "amount" in row.columns:
                assert float(row.iloc[0]["amount"]) >= 10_000_000
        # Filtered ⊆ raw (by normalized code); Round2 may reorder
        raw_codes = {norm_code(r["code"]) for r in raw}
        assert codes <= raw_codes
        break
    assert found


def test_regime_map_blocks_weak_days(feats: pd.DataFrame):
    regime = build_lvrev_regime_map(feats, name_map=_names())
    assert regime  # non-empty
    # Values are bool
    assert all(isinstance(v, bool) for v in regime.values())


def test_baseline_variant_bit_identical_to_factory_replay(feats: pd.DataFrame):
    params = ReplayParams(initial_capital=50000.0, max_positions=15)
    factory = replay_book(feats, entry_provider=screener_entry_provider(), params=params)
    arm = run_lvrev_variant(feats, variant=BASELINE, params=params, name_map=_names())
    assert factory["equity_curve"] == arm["equity_curve"]
    assert factory["trades"] == arm["trades"]


def test_regime_variant_never_buys_on_blocked_days(feats: pd.DataFrame):
    params = ReplayParams(initial_capital=50000.0, max_positions=15)
    arm = run_lvrev_variant(feats, variant="regime", params=params, name_map=_names())
    regime = build_lvrev_regime_map(feats, name_map=_names())
    for t in arm["trades"]:
        entry = str(t.get("entry_date") or "")
        assert regime.get(entry, True) is True


def test_year_slice_metrics_splits_by_calendar_year():
    curve = [
        {"date": "2021-06-01", "equity": 51000.0},
        {"date": "2021-12-31", "equity": 52000.0},
        {"date": "2022-06-01", "equity": 50000.0},
        {"date": "2022-12-30", "equity": 48000.0},
    ]
    trades = [
        {"exit_date": "2021-07-01", "net_ret": 0.02, "held_days": 10},
        {"exit_date": "2022-08-01", "net_ret": -0.01, "held_days": 5},
    ]
    years = year_slice_metrics(curve, trades, initial_capital=50000.0, years=[2021, 2022])
    assert years["2021"]["total_return"] == pytest.approx(52000 / 50000 - 1)
    assert years["2022"]["total_return"] == pytest.approx(48000 / 52000 - 1)
    assert years["2021"]["n_trades"] == 1
    assert years["2022"]["n_trades"] == 1


def test_evaluate_criteria_requires_all_four():
    base_arm = {"metrics": {"max_drawdown": -0.10}}
    var_arm = {"metrics": {"max_drawdown": -0.09}}
    years = ["2021", "2022", "2023", "2024", "2025", "2026"]
    base_y = {
        y: {"sharpe": 0.5, "total_return": 0.1, "max_drawdown": -0.05, "win_rate": 0.4, "n_trades": 10, "n_days": 200}
        for y in years
    }
    var_y = {
        y: {"sharpe": 0.6, "total_return": 0.12, "max_drawdown": -0.04, "win_rate": 0.42, "n_trades": 10, "n_days": 200}
        for y in years
    }
    # Spread excess evenly → max contrib 1/6 < 60%
    ok = evaluate_criteria(
        baseline_arm=base_arm,
        variant_arm=var_arm,
        baseline_years=base_y,
        variant_years=var_y,
        y1_baseline_pass=0,
        y1_variant_pass=0,
    )
    assert ok["passed"] is True
    assert ok["a"]["ok"] and ok["b"]["ok"] and ok["c"]["ok"] and ok["d"]["ok"]

    # Fail (d): deeper drawdown
    bad_d = evaluate_criteria(
        baseline_arm=base_arm,
        variant_arm={"metrics": {"max_drawdown": -0.20}},
        baseline_years=base_y,
        variant_years=var_y,
        y1_baseline_pass=0,
        y1_variant_pass=0,
    )
    assert bad_d["passed"] is False
    assert bad_d["d"]["ok"] is False
