"""M-R4 factor IC summary tests (zero public net)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_platform_research.factor_ic import (
    DEFAULT_ADMISSION,
    DEFAULT_MAX_CORR,
    admit_factor,
    build_factor_ic_report,
    select_enabled,
    spearman_rank_ic,
    summarize_factor_ic,
)


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
    assert out["std_ic"] is not None
    assert out["icir"] is not None
    assert out["liveTradingEnabled"] is False
    assert out["environment"] == "SIMULATE"


def test_summarize_factor_ic_from_rows() -> None:
    from stock_platform_research.factor_ic import summarize_factor_ic_from_rows

    rows = [
        {"asof": "2026-01-02", "factor": 1, "forward_return": 0.01},
        {"asof": "2026-01-02", "factor": 2, "forward_return": 0.02},
        {"asof": "2026-01-02", "factor": 3, "forward_return": 0.03},
        {"asof": "2026-01-03", "factor": 3, "forward_return": -0.01},
        {"asof": "2026-01-03", "factor": 2, "forward_return": 0.0},
        {"asof": "2026-01-03", "factor": 1, "forward_return": 0.02},
    ]
    out = summarize_factor_ic_from_rows(rows)
    assert out["n_dates"] == 2
    assert out["icir"] is not None


# --------------------------------------------------------------------------- #
# S2 — IC/ICIR + orthogonality admission
# --------------------------------------------------------------------------- #

def _feats(*, n_codes: int = 20, n_days: int = 260, seed: int = 11) -> pd.DataFrame:
    """Synthetic PIT feature frame (no ``pct_chg`` — see test_factors docstring)."""
    from stock_platform_research.factors import build_feature_frame

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days).strftime("%Y-%m-%d")
    rows: list[dict[str, object]] = []
    for c in range(n_codes):
        code = f"{600000 + c}.SH"
        rets = rng.normal(0.0002, 0.008 + 0.0005 * c, n_days)
        close = 12.0 * np.cumprod(1.0 + rets)
        for d, cl in zip(dates, close, strict=True):
            rows.append(
                {
                    "code": code,
                    "date": d,
                    "close": float(cl),
                    "amount": float(10 ** rng.uniform(7.0, 8.5)),
                }
            )
    return build_feature_frame(pd.DataFrame(rows))


def test_admit_factor_checks_every_gate() -> None:
    base = {"n_dates": 40, "mean_ic": 0.05, "icir": 0.30}
    assert admit_factor(base, direction=1)["passed"] is True
    # sign must agree with the declared direction
    assert admit_factor(base, direction=-1)["passed"] is False
    # each threshold is a hard gate
    assert admit_factor({**base, "mean_ic": 0.01}, direction=1)["passed"] is False
    assert admit_factor({**base, "icir": 0.05}, direction=1)["passed"] is False
    thin = admit_factor({**base, "n_dates": 5}, direction=1)
    assert thin["passed"] is False
    assert thin["checks"] == {"n_dates": False, "abs_ic": True, "abs_icir": True, "sign": True}
    assert thin["reasons"] and "截面" in thin["reasons"][0]


def test_admit_factor_negative_ic_with_negative_direction_passes() -> None:
    out = admit_factor({"n_dates": 30, "mean_ic": -0.06, "icir": -0.4}, direction=-1)
    assert out["passed"] is True


def test_admit_factor_threshold_override_and_defaults() -> None:
    assert DEFAULT_ADMISSION["min_abs_ic"] == 0.02
    out = admit_factor(
        {"n_dates": 10, "mean_ic": None, "icir": None},
        direction=1,
        thresholds={"min_dates": 5},
    )
    assert out["checks"]["n_dates"] is True
    assert out["checks"]["abs_ic"] is False and out["checks"]["abs_icir"] is False


def test_select_enabled_incumbents_first_then_orthogonal() -> None:
    corr = pd.DataFrame(
        [[1.0, 0.9, 0.1], [0.9, 1.0, 0.2], [0.1, 0.2, 1.0]],
        index=["a", "b", "c"],
        columns=["a", "b", "c"],
    )
    out = select_enabled(["a", "b", "c"], {"a": True, "b": True, "c": True}, corr, max_corr=0.7)
    assert out["enabled"] == ["a", "c"]
    assert out["redundant"] == ["b"]
    assert out["redundant"] and out["redundancy"]["b"][0] == "a"
    assert abs(out["redundancy"]["b"][1] - 0.9) < 1e-9


def test_select_enabled_rejects_failed_gate_and_honours_ceiling() -> None:
    out = select_enabled(["a", "b"], {"a": False, "b": True}, None)
    assert out["rejected"] == ["a"] and out["enabled"] == ["b"]

    corr = pd.DataFrame([[1.0, 0.99], [0.99, 1.0]], index=["a", "b"], columns=["a", "b"])
    loose = select_enabled(["a", "b"], {"a": True, "b": True}, corr, max_corr=1.0)
    assert loose["enabled"] == ["a", "b"] and loose["redundant"] == []


def test_default_orthogonality_ceiling() -> None:
    assert DEFAULT_MAX_CORR == 0.7


def test_build_factor_ic_report_contract() -> None:
    rep = build_factor_ic_report(_feats(), horizon=20, sample_every=5, min_names=10)
    assert rep["ok"] is True
    assert rep["nDates"] > 0
    assert rep["maxCorr"] == DEFAULT_MAX_CORR
    names = set(rep["factors"])
    assert set(rep["enabled"]) | set(rep["redundant"]) | set(rep["rejected"]) == names
    assert rep["disabled"] == rep["rejected"] + rep["redundant"]
    assert rep["correlation"] is not None
    assert set(rep["correlation"]) == names
    assert rep["liveTradingEnabled"] is False
    assert rep["environment"] == "SIMULATE"


def test_build_factor_ic_report_zero_ceiling_keeps_at_most_one() -> None:
    rep = build_factor_ic_report(
        _feats(), horizon=20, sample_every=5, min_names=10, max_corr=0.0
    )
    assert rep["ok"] is True
    assert len(rep["enabled"]) <= 1


def test_build_factor_ic_report_fail_closed() -> None:
    assert build_factor_ic_report(pd.DataFrame())["ok"] is False
    assert build_factor_ic_report(_feats(), factors=["nope"])["ok"] is False
    assert build_factor_ic_report(_feats(), factors=[])["ok"] is False
    empty = build_factor_ic_report(pd.DataFrame())["rejected"]
    assert empty == []
