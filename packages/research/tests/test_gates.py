"""Equivalence proof: vectorised ``apply_entry_gates`` == original row-wise loop.

The row-wise port lived in the engine; B1 vectorised it for full-market speed.
These tests pin the semantics so the live and backtest paths keep sharing one
definition.
"""

from __future__ import annotations

import random

import pandas as pd

from stock_platform_research.gates import EntryGateParams, apply_entry_gates

NAN = float("nan")


def _reference_apply_entry_gates(df: pd.DataFrame, reversal_q: float = 0.30) -> pd.Series:
    """Original a-stock-engine port, kept as the equivalence oracle."""
    if len(df) == 0:
        return pd.Series([], dtype=bool)

    keep = pd.Series(True, index=df.index)
    vol_med = (
        float(df["vol20"].median())
        if "vol20" in df.columns and df["vol20"].notna().any()
        else float("inf")
    )
    chg_q = (
        float(df["rev_chg"].quantile(reversal_q))
        if "rev_chg" in df.columns and df["rev_chg"].notna().any()
        else -0.05
    )

    for idx, row in df.iterrows():
        close = row.get("close")
        ma20 = row.get("ma20")
        ma60 = row.get("ma60")
        vol = row.get("vol20")
        rev = row.get("rev_chg")

        if ma20 is not None and ma60 is not None and not pd.isna(ma20) and not pd.isna(ma60):
            if ma20 <= ma60:
                keep[idx] = False
                continue
        if ma20 is not None and close is not None and not pd.isna(ma20) and ma20 > 0:
            if close < ma20 * 0.93:
                keep[idx] = False
                continue
        if rev is not None and not pd.isna(rev) and rev > chg_q:
            keep[idx] = False
            continue
        if ma60 is not None and close is not None and not pd.isna(ma60) and ma60 > 0:
            if close < ma60 * 0.93:
                keep[idx] = False
                continue
        if vol is not None and not pd.isna(vol) and vol_med != float("inf"):
            if vol > vol_med:
                keep[idx] = False
                continue
    return keep


def _random_frame(n: int, seed: int) -> pd.DataFrame:
    rnd = random.Random(seed)
    rows = []
    for _ in range(n):
        close = rnd.uniform(2.0, 60.0)
        rows.append(
            {
                "close": NAN if rnd.random() < 0.05 else close,
                "ma20": NAN if rnd.random() < 0.08 else close * rnd.uniform(0.85, 1.15),
                "ma60": NAN if rnd.random() < 0.08 else close * rnd.uniform(0.85, 1.15),
                "vol20": NAN if rnd.random() < 0.08 else rnd.uniform(0.0, 0.06),
                "rev_chg": NAN if rnd.random() < 0.08 else rnd.uniform(-0.4, 0.4),
            }
        )
    return pd.DataFrame(rows)


def test_vectorised_matches_reference_on_random_data():
    for seed in range(12):
        df = _random_frame(400, seed)
        got = list(apply_entry_gates(df))
        want = list(_reference_apply_entry_gates(df))
        assert got == want, f"mismatch at seed={seed}"


def test_equivalence_holds_with_missing_columns():
    df = _random_frame(200, 99).drop(columns=["ma60"])
    got = list(apply_entry_gates(df))
    want = list(_reference_apply_entry_gates(df))
    assert got == want


def test_empty_frame_returns_empty_bool_series():
    out = apply_entry_gates(pd.DataFrame())
    assert len(out) == 0
    assert out.dtype == bool


def test_all_gates_reject_extreme_row():
    df = pd.DataFrame(
        [
            {
                "close": 1.0,  # way below both MAs
                "ma20": 10.0,
                "ma60": 20.0,  # ma20 <= ma60 -> reject
                "vol20": 0.5,  # above median -> reject
                "rev_chg": 0.9,  # above quantile -> reject
            }
        ]
    )
    assert list(apply_entry_gates(df)) == [False]


# ---------------------------------------------------------------------------
# S3: the hard-coded constants are now one EntryGateParams object.
#
# The oracle above bakes in ``0.93`` and the vol-median filter; asserting the
# parameterised gate still equals it proves S3 changed *no* semantics, only the
# route by which a caller may move a knob.
# ---------------------------------------------------------------------------
def test_params_object_default_matches_reference_loop():
    for seed in range(6):
        df = _random_frame(300, seed)
        got = list(apply_entry_gates(df, params=EntryGateParams()))
        want = list(_reference_apply_entry_gates(df))
        assert got == want, f"EntryGateParams() drifted at seed={seed}"


def test_params_object_ma_band_matches_explicit_scalar():
    """Bumping ``ma20_band``/``ma60_band`` together equals the old 0.93 path."""
    df = _random_frame(300, 7)
    via_params = list(apply_entry_gates(df, params=EntryGateParams(ma20_band=0.93, ma60_band=0.93)))
    via_default = list(apply_entry_gates(df))
    assert via_params == via_default
