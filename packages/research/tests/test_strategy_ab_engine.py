"""``S1`` — engine-backed strategy A/B: two configs, one loop, one yardstick.

The point of S1 is that a factor / gate change can now be compared on the *same*
engine the backtest and the logged-picks replay use, with a 复盘 (review) block
per arm. These tests pin (a) the config→engine parity with ``run_portfolio_backtest``
and (b) the A/B contract (single-definition identity, delta, gate selectivity).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.backtest import prepare_book_frame, run_portfolio_backtest
from stock_platform_research.book_replay import (
    ReplayParams,
    replay_book,
    screener_entry_provider,
)
from stock_platform_research.strategy_ab import (
    AB_METRIC_KEYS,
    compare_strategy_ab_engine,
    compare_strategy_ab_from_bars,
    config_entry_provider,
    run_config_book,
)
from stock_platform_research.strategy_config import (
    DEFAULT_MIN_PICK_SCORE,
    StrategyConfig,
    load_strategy_config,
)


def _bars(seed: int = 7, periods: int = 170) -> pd.DataFrame:
    """Six synthetic stock codes with distinct trend / vol (enough for MA60)."""
    rng = np.random.default_rng(seed)
    codes = ["000001", "600000", "600519", "000002", "601318", "300750"]
    dates = pd.bdate_range("2024-01-01", periods=periods)
    frames = []
    for i, code in enumerate(codes):
        drift = 0.0014 - 0.0009 * i
        vol = 0.014 + 0.0045 * i
        rets = rng.normal(drift, vol, len(dates))
        if i == 0:  # a mild pullback inside an uptrend -> oversold but above MA60
            rets[-25:] = rng.normal(-0.0016, 0.0035, 25)
        px = 10.0 * np.cumprod(1.0 + rets)
        frames.append(
            pd.DataFrame(
                {
                    "code": code,
                    "date": [d.strftime("%Y-%m-%d") for d in dates],
                    "close": np.round(px, 3),
                    "pct_chg": np.round(rets * 100.0, 4),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_baseline_config_reproduces_portfolio_backtest_bit_for_bit() -> None:
    """A default config == ``run_portfolio_backtest`` (same loop, same knobs)."""
    bars = _bars()
    bt = run_portfolio_backtest(bars)
    feats = prepare_book_frame(bars)
    ab = run_config_book(feats, StrategyConfig(id="baseline", version="1"))

    assert bt["ok"] is True and ab["ok"] is True
    assert ab["trades"] == bt["trades"]
    assert ab["equity_curve"] == bt["equity_curve"]
    assert ab["open_positions"] == bt["open_positions"]
    assert ab["metrics"] == bt["metrics"]
    assert ab["final_equity"] == bt["final_equity"]


def test_config_entry_provider_matches_shared_screener_provider() -> None:
    """``config_entry_provider`` is literally the shared screener provider."""
    feats = prepare_book_frame(_bars())
    cfg = StrategyConfig(
        id="x", version="1", reversal_q=0.40, gates={"min_pick_score": 0.70}
    )
    a = replay_book(
        feats, entry_provider=config_entry_provider(cfg), params=ReplayParams()
    )
    b = replay_book(
        feats,
        entry_provider=screener_entry_provider(
            reversal_q=0.40,
            min_pick_score=0.70,
            value_factor=False,
            weights=cfg.weights,
        ),
        params=ReplayParams(),
    )
    assert a["trades"] == b["trades"]
    assert a["equity_curve"] == b["equity_curve"]


def test_engine_compare_contract() -> None:
    feats = prepare_book_frame(_bars())
    out = compare_strategy_ab_engine(
        feats,
        StrategyConfig(id="A", version="1"),
        StrategyConfig(
            id="B",
            version="1",
            weights={"vol": 0.3, "rev": 0.7, "value": 0.0, "q": 0.0, "g": 0.0},
        ),
    )
    assert out["ok"] is True
    assert out["replacesPicks"] is False
    assert out["liveTradingEnabled"] is False
    assert out["panelSource"] == "engine"
    # S1: both arms provably run the X4/B5 single definitions.
    assert out["sameDefinition"] == {
        "singleLoop": True,
        "singleEntryProvider": True,
        "singleMetrics": True,
        "singleExitDefinition": True,
    }
    assert set(AB_METRIC_KEYS) <= set(out["delta"])
    assert out["winner"] in {"A", "B", "tie"}
    assert "metrics" in out["a"] and "review" in out["a"]
    assert "metrics" in out["b"] and "review" in out["b"]
    # delta is literally B − A on the shared metric block.
    assert out["delta"]["final_equity"] == pytest.approx(
        out["b"]["metrics"]["final_equity"] - out["a"]["metrics"]["final_equity"]
    )
    assert out["delta"]["n_trades"] == pytest.approx(
        out["b"]["metrics"]["n_trades"] - out["a"]["metrics"]["n_trades"]
    )


def test_stricter_gate_never_enters_more() -> None:
    """A higher ``min_pick_score`` gate can only shrink the entered set."""
    feats = prepare_book_frame(_bars())
    loose = run_config_book(
        feats, StrategyConfig(id="loose", version="1", gates={"min_pick_score": 0.50})
    )
    strict = run_config_book(
        feats, StrategyConfig(id="strict", version="1", gates={"min_pick_score": 0.90})
    )
    entered_loose = len(loose["trades"]) + len(loose["open_positions"])
    entered_strict = len(strict["trades"]) + len(strict["open_positions"])
    assert entered_strict <= entered_loose


def test_gate_default_and_alias_parsing() -> None:
    assert StrategyConfig(id="d", version="1").min_pick_score == DEFAULT_MIN_PICK_SCORE
    flat = load_strategy_config({"id": "g", "min_pick_score": 0.91})
    assert flat.min_pick_score == pytest.approx(0.91)
    assert flat.gates["min_pick_score"] == pytest.approx(0.91)
    nested = load_strategy_config(
        {"id": "g2", "gates": {"min_pick_score": 0.88, "other": 2}}
    )
    assert nested.min_pick_score == pytest.approx(0.88)
    assert nested.gate("other") == pytest.approx(2.0)
    assert nested.gate("missing") is None


def test_compare_from_bars_end_to_end_and_fail_closed() -> None:
    bars = _bars()
    out = compare_strategy_ab_from_bars(bars, "lvrev-default-v1", "lvrev-rev-heavy-v1")
    assert out["ok"] is True
    assert out["universe"] == "stock"
    assert out["a"]["configId"] == "lvrev-default-v1"
    assert out["b"]["configId"] == "lvrev-rev-heavy-v1"
    assert all(out["sameDefinition"].values())

    empty = compare_strategy_ab_from_bars(
        bars.iloc[0:0], "lvrev-default-v1", "lvrev-rev-heavy-v1"
    )
    assert empty["ok"] is False
    assert empty["reason"] == "no bars in range"
    assert empty["liveTradingEnabled"] is False


def test_review_block_counts_direction_and_pending() -> None:
    feats = prepare_book_frame(_bars())
    out = run_config_book(feats, StrategyConfig(id="rv", version="1"))
    review = out["review"]
    assert review["settledCount"] == len(out["trades"])
    assert review["pendingCount"] == len(out["open_positions"])
    if review["settledCount"]:
        assert review["directionAccuracy"] == pytest.approx(
            review["directionHits"] / review["settledCount"]
        )
    else:
        # empty book must not fabricate a 0 accuracy
        assert review["directionAccuracy"] is None


def test_unknown_config_id_raises() -> None:
    with pytest.raises(FileNotFoundError):
        run_config_book(prepare_book_frame(_bars()), "no-such-config-xyz")
