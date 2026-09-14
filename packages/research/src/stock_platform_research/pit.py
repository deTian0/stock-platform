"""Minimal PIT long-only backtest helpers (signal day vs trade day separation)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .gates import apply_entry_gates
from .lvrev import score_lvrev

# Columns that must never be used as features on signal day T if they encode T+k.
FORBIDDEN_LOOKAHEAD = frozenset(
    {
        "next_open",
        "next_close",
        "fwd_ret_1d",
        "fwd_ret_5d",
        "future_close",
        "t1_open",
    }
)


def assert_no_lookahead_columns(feature_columns: list[str] | set[str]) -> None:
    bad = set(feature_columns) & FORBIDDEN_LOOKAHEAD
    if bad:
        raise ValueError(
            f"lookahead feature columns forbidden on signal day: {sorted(bad)}. "
            "Score using only as-of-T fields; execute at next session open."
        )


def run_pit_long_only(
    panel: pd.DataFrame,
    *,
    top_n: int = 1,
    reversal_q: float = 0.30,
    value_factor: bool = False,
    weights: dict | None = None,
    feature_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Run a tiny long-only PIT loop.

    Expected ``panel`` columns:
      trade_date, symbol, open, close, vol20, rev_chg, ma20, ma60
      (+ optional debt_ratio, pb, ps_ttm, pe, ...)

    Rules:
      - On date T, score using only as-of-T feature columns (no next_* / fwd_*).
      - Signal at T close; fill at T+1 open: ret = open_{T+1} / close_T - 1.
    """
    required = {"trade_date", "symbol", "open", "close", "vol20", "rev_chg", "ma20", "ma60"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing columns: {sorted(missing)}")

    feats = feature_columns or [
        c
        for c in panel.columns
        if c not in {"trade_date", "symbol", "open", "close"}
    ]
    assert_no_lookahead_columns(feats)

    df = panel.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.normalize()
    dates = sorted(df["trade_date"].unique())
    if len(dates) < 2:
        return {"trades": [], "equity_curve": [], "n_dates": len(dates), "final_equity": 1.0}

    df = df.sort_values(["symbol", "trade_date"])
    df["_next_open"] = df.groupby("symbol")["open"].shift(-1)

    trades: list[dict[str, Any]] = []
    equity = 1.0
    curve: list[dict[str, Any]] = []

    for d in dates[:-1]:
        cross = df[df["trade_date"] == d].copy()
        score_input = cross.drop(columns=["_next_open"], errors="ignore")
        assert_no_lookahead_columns(score_input.columns)
        scored = score_lvrev(score_input, value_factor=value_factor, weights=weights)
        mask = apply_entry_gates(scored, reversal_q=reversal_q)
        picks = scored.loc[mask].head(top_n)
        if picks.empty:
            curve.append({"trade_date": d.date().isoformat(), "equity": equity, "n_picks": 0})
            continue

        day_rets: list[float] = []
        for idx, row in picks.iterrows():
            nxt = cross.loc[idx, "_next_open"]
            if pd.isna(nxt) or pd.isna(row["close"]) or float(row["close"]) == 0:
                continue
            ret = float(nxt) / float(row["close"]) - 1.0
            day_rets.append(ret)
            trades.append(
                {
                    "signal_date": d.date().isoformat(),
                    "symbol": row["symbol"],
                    "score": float(row["composite_score"]),
                    "fill_open": float(nxt),
                    "signal_close": float(row["close"]),
                    "ret": ret,
                }
            )
        if day_rets:
            equity *= 1.0 + (sum(day_rets) / len(day_rets))
        curve.append(
            {
                "trade_date": d.date().isoformat(),
                "equity": equity,
                "n_picks": len(day_rets),
            }
        )

    return {
        "trades": trades,
        "equity_curve": curve,
        "n_dates": len(dates),
        "final_equity": equity,
    }
