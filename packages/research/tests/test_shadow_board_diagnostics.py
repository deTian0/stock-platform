"""Read-only S4/S5 pool diagnostics: forward returns are outcomes, pools stay PIT."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_platform_research.shadow_board.backtest import prepare_shadow_frame
from stock_platform_research.shadow_board.diagnostics import (
    POOLS,
    add_forward_returns,
    collect_pools,
    render_markdown,
    simulate_exits,
    summarize,
)

N_CODES = 40
N_DAYS = 90


def _bars(seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=N_DAYS)
    rows = []
    for i in range(N_CODES):
        code = f"{600000 + i:06d}.SH"
        px = 10.0 + i
        for d in days:
            pct = float(np.clip(rng.normal(0.05, 2.0), -9.0, 9.0))
            px *= 1.0 + pct / 100.0
            rows.append({"code": code, "date": d.date().isoformat(), "close": round(px, 3),
                         "pct_chg": round(pct / 100.0, 6), "amount": 5e7 + i * 1e7})
    return pd.DataFrame(rows)


def _names() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"样本{i}" for i in range(N_CODES)}


def _feats() -> pd.DataFrame:
    return prepare_shadow_frame(_bars())


def test_forward_returns_match_close_ratio() -> None:
    fwd = add_forward_returns(_feats())
    one = fwd[fwd["code"] == "600003.SH"].reset_index(drop=True)
    c = one["close"].astype("float64")
    assert np.isclose(one.loc[30, "fwd_5"], c[35] / c[30] - 1.0)
    assert np.isclose(one.loc[30, "fwdd_5"], c[36] / c[31] - 1.0)
    assert pd.isna(one["fwd_5"].iloc[-1])  # tail has no future: NaN, not 0


def test_pools_ignore_future_bars() -> None:
    feats = _feats()
    cut = feats["trade_date"].sort_values().unique()[60]
    full = add_forward_returns(feats)
    trunc = add_forward_returns(feats[feats["trade_date"] <= cut])
    a, _ = collect_pools(full[full["trade_date"] == cut], name_map=_names())
    b, _ = collect_pools(trunc[trunc["trade_date"] == cut], name_map=_names())
    key = ["pool", "rank", "code"]
    assert not a.empty
    assert a[key].reset_index(drop=True).equals(b[key].reset_index(drop=True))


def test_summary_covers_pools_and_exit_sim() -> None:
    fwd = add_forward_returns(_feats())
    cands, days = collect_pools(fwd, name_map=_names(), every=5)
    cands = simulate_exits(fwd, cands)
    assert set(cands["ex_reason"]) <= {"open", "stop_loss", "target", "trend_break", "trail_stop", "max_hold"}
    s = summarize(cands, days)
    assert {"S3", "S4", "S5", "RANDOM"} <= set(s["pools"]) <= set(POOLS)
    assert "ic_s4_5" in s["ic"] or days.empty
    md = render_markdown(s, {"区间": "test"})
    assert "S4" in md and "SIMULATE" in md


def test_no_name_map_means_no_s3_s4_pools() -> None:
    fwd = add_forward_returns(_feats())
    cands, _ = collect_pools(fwd, name_map=None, every=10)
    assert not set(cands["pool"]) & {"S3", "S4", "S4inv"}
