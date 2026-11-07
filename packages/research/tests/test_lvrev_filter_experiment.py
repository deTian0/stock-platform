"""lvrev entry-filter / cooldown experiments (docs/plans/lvrev-entry-filter.md)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.book_replay import (
    EntryContext,
    ReplayParams,
    replay_book,
    screener_entry_provider,
)
from stock_platform_research.lvrev_filter_experiment import (
    AMOUNT_FLOOR,
    COOLDOWN_DAYS,
    NEAR_LIMIT_PCT,
    VARIANTS,
    compare_lvrev_filters,
    filtered_entry_provider,
    run_filter_variant,
)
from stock_platform_research.rules import CooldownPolicy
from stock_platform_research.shadow_board.backtest import prepare_shadow_frame

N_CODES = 24
N_DAYS = 100


def _bars(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-02", periods=N_DAYS)
    rows = []
    for i in range(N_CODES):
        px = 10.0 + i * 0.3
        for k, d in enumerate(days):
            pct = float(rng.normal(0.2, 2.5))
            pct = max(min(pct, 9.5), -9.5)
            # Force some near-limit days
            if k % 17 == i % 7:
                pct = 8.5
            px *= 1.0 + pct / 100.0
            rows.append(
                {
                    "code": f"{600000 + i:06d}.SH",
                    "date": d.date().isoformat(),
                    "close": round(px, 3),
                    "pct_chg": round(pct, 4),
                    "amount": 8e7 if i % 4 else 1e6,  # some below 50m floor
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def feats() -> pd.DataFrame:
    return prepare_shadow_frame(_bars())


def test_variant_ids_match_plan():
    assert VARIANTS == ("near_limit7", "amount50m", "cooldown5")
    assert NEAR_LIMIT_PCT == 7.0
    assert AMOUNT_FLOOR == 50_000_000.0
    assert COOLDOWN_DAYS == 5


def test_filtered_provider_default_matches_screener(feats: pd.DataFrame):
    factory = screener_entry_provider()
    wrapped = filtered_entry_provider()
    day, frame = next(iter(feats.groupby("trade_date", sort=True)))
    ctx = EntryContext(
        day_index=0,
        day=pd.Timestamp(day).date().isoformat(),
        frame=frame,
        positions={},
        cash=50000.0,
        equity=50000.0,
        last_exit_idx={},
        params=ReplayParams(),
    )
    a = factory(ctx)
    b = wrapped(ctx)
    assert [r["code"] for r in a] == [r["code"] for r in b]


def test_near_limit_drops_high_pct(feats: pd.DataFrame, monkeypatch):
    # Screener rarely surfaces near-limit names on synthetic bars; stub the base.
    fixed = [
        {"code": "600000.SH", "close": 10.0, "pct_chg": 8.2},
        {"code": "600001.SH", "close": 10.0, "pct_chg": 3.0},
        {"code": "600002.SH", "close": 10.0, "pct_chg": None},
    ]
    monkeypatch.setattr(
        "stock_platform_research.lvrev_filter_experiment.screener_entry_provider",
        lambda **_kw: (lambda _ctx: list(fixed)),
    )
    day, frame = next(iter(feats.groupby("trade_date", sort=True)))
    ctx = EntryContext(
        day_index=0,
        day=pd.Timestamp(day).date().isoformat(),
        frame=frame,
        positions={},
        cash=50000.0,
        equity=50000.0,
        last_exit_idx={},
        params=ReplayParams(),
    )
    out = filtered_entry_provider(near_limit_pct=NEAR_LIMIT_PCT)(ctx)
    codes = [str(r["code"]) for r in out]
    assert "600000.SH" not in codes
    assert "600001.SH" in codes
    assert "600002.SH" in codes  # missing pct → keep


def test_amount_floor_fail_closed(feats: pd.DataFrame):
    provider = filtered_entry_provider(amount_min=AMOUNT_FLOOR)
    for day, frame in list(feats.groupby("trade_date", sort=True))[:20]:
        ctx = EntryContext(
            day_index=0,
            day=pd.Timestamp(day).date().isoformat(),
            frame=frame,
            positions={},
            cash=50000.0,
            equity=50000.0,
            last_exit_idx={},
            params=ReplayParams(),
        )
        for r in provider(ctx):
            code = str(r["code"])
            amt = float(frame.loc[frame["code"].astype(str) == code, "amount"].iloc[0])
            assert amt >= AMOUNT_FLOOR


def test_baseline_bit_identical_to_factory(feats: pd.DataFrame):
    params = ReplayParams(initial_capital=50000.0, max_positions=8)
    factory = replay_book(feats, entry_provider=screener_entry_provider(), params=params)
    base = run_filter_variant(feats, variant="baseline", params=params)
    assert base["final_equity"] == factory["final_equity"]
    assert len(base["trades"]) == len(factory["trades"])
    assert base["equity_curve"] == factory["equity_curve"]


def test_cooldown5_uses_policy():
    p = ReplayParams(cooldown_policy=CooldownPolicy(cooldown_days=0))
    # smoke: variant runs without error on empty-ish path
    out = run_filter_variant(
        prepare_shadow_frame(_bars(seed=3).head(200)),
        variant="cooldown5",
        params=p,
    )
    assert out["ok"] is True
    assert out["variant"] == "cooldown5"


def test_compare_smoke(feats: pd.DataFrame):
    out = compare_lvrev_filters(
        feats,
        variants=["near_limit7"],
        params=ReplayParams(max_positions=8),
        run_y1=False,
    )
    assert out["ok"] is True
    assert "near_limit7" in out["comparisons"]
    assert "passed" in out["comparisons"]["near_limit7"]["criteria"]
