"""lvrev ``trail_tp`` production opt-in switch (ADR 0094).

Pins: default OFF ⇒ run is bit-identical to the pre-switch factory call;
explicit flag wins over env; env ``STOCK_PLATFORM_LVREV_TRAIL_TP=1`` turns it on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.backtest import (
    ENV_LVREV_TRAIL_TP,
    resolve_trail_tp,
    run_portfolio_backtest,
)


def _bars(seed: int = 11, n_codes: int = 20, n_days: int = 160) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-02", periods=n_days)
    rows = []
    for i in range(n_codes):
        px = 10.0 + i * 0.5
        for k, d in enumerate(days):
            common = 1.0 if (k // 25) % 2 == 0 else -1.5
            pct = float(np.clip(rng.normal(common, 2.5), -9.0, 9.0))
            px *= 1.0 + pct / 100.0
            rows.append(
                {
                    "code": f"{600000 + i:06d}.SH",
                    "date": d.date().isoformat(),
                    "close": round(px, 3),
                    "pct_chg": round(pct, 4),
                }
            )
    return pd.DataFrame(rows)


def test_resolve_default_off_and_env_switch():
    assert resolve_trail_tp(None, env={}) is False
    assert resolve_trail_tp(None, env={ENV_LVREV_TRAIL_TP: "0"}) is False
    assert resolve_trail_tp(None, env={ENV_LVREV_TRAIL_TP: "1"}) is True
    assert resolve_trail_tp(None, env={ENV_LVREV_TRAIL_TP: "On"}) is True


def test_explicit_flag_wins_over_env():
    env = {ENV_LVREV_TRAIL_TP: "1"}
    assert resolve_trail_tp(False, env=env) is False
    assert resolve_trail_tp(True, env={}) is True


def test_default_off_is_bit_identical_to_explicit_false(monkeypatch):
    monkeypatch.delenv(ENV_LVREV_TRAIL_TP, raising=False)
    bars = _bars()
    default = run_portfolio_backtest(bars, initial_capital=50000.0)
    explicit = run_portfolio_backtest(bars, initial_capital=50000.0, trail_tp=False)
    assert default["params"]["exit_policy"]["trail_tp"] is False
    assert default["equity_curve"] == explicit["equity_curve"]
    assert default["trades"] == explicit["trades"]


def test_switch_on_routes_through_trail_tp(monkeypatch):
    # seed 5 triggers the branch (4 trail_tp exits in the 160-day sample);
    # the default seed 11 does not, so it cannot prove routing.
    bars = _bars(seed=5)
    monkeypatch.delenv(ENV_LVREV_TRAIL_TP, raising=False)
    off = run_portfolio_backtest(bars, initial_capital=50000.0)
    monkeypatch.setenv(ENV_LVREV_TRAIL_TP, "1")
    on = run_portfolio_backtest(bars, initial_capital=50000.0)
    assert on["params"]["exit_policy"]["trail_tp"] is True
    assert off["params"]["exit_policy"]["trail_tp"] is False
    # Turning the switch on must actually reach the exit rule: some exit
    # reason in the trade log is the experimental branch.
    reasons = [str(t.get("reason") or "") for t in on["trades"]]
    assert any(r.startswith("trail_tp(") for r in reasons)
    assert not any(str(t.get("reason") or "").startswith("trail_tp(") for t in off["trades"])
