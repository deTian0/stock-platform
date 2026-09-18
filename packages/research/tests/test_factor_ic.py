"""M-R4 factor IC summary tests (zero public net)."""

from __future__ import annotations

from stock_platform_research.factor_ic import spearman_rank_ic, summarize_factor_ic


def test_spearman_rank_ic_perfect() -> None:
    ic = spearman_rank_ic([1, 2, 3, 4], [0.1, 0.2, 0.3, 0.4])
    assert ic == 1.0


def test_spearman_rank_ic_too_few() -> None:
    assert spearman_rank_ic([1, 2], [0.1, 0.2]) is None


def test_summarize_factor_ic_dates() -> None:
    obs = [
        {
            "asof": "2026-01-02",
            "values": [
                {"factor": 1, "forward_return": 0.01},
                {"factor": 2, "forward_return": 0.02},
                {"factor": 3, "forward_return": 0.03},
            ],
        },
        {
            "asof": "2026-01-03",
            "values": [
                {"factor": 3, "forward_return": -0.01},
                {"factor": 2, "forward_return": 0.0},
                {"factor": 1, "forward_return": 0.02},
            ],
        },
    ]
    out = summarize_factor_ic(obs)
    assert out["ok"] is True
    assert out["n_dates"] == 2
    assert out["mean_ic"] is not None
    assert out["liveTradingEnabled"] is False
    assert out["environment"] == "SIMULATE"
