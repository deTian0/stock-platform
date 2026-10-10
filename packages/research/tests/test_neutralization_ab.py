"""``S4`` — neutralization A/B contract, industry loader and CLI.

The A/B must (a) leave the raw arm **bit-identical** to the pre-``S4`` screener book
even when an industry column is present, and (b) prove both arms ran the same
engine (``sameDefinition``), so ``delta`` is attributable to neutralization.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from stock_platform_research.backtest import prepare_book_frame
from stock_platform_research.backtest_cli import load_engine_industry
from stock_platform_research.book_replay import (
    EntryContext,
    ReplayParams,
    screener_entry_provider,
)
from stock_platform_research.gates import EntryGateParams
from stock_platform_research.neutralization import NeutralizeParams, attach_industry
from stock_platform_research.neutralization_ab import (
    compare_neutralization_ab,
    neutralization_ab_from_bars,
    run_neutralization_book,
)
from stock_platform_research.neutralization_cli import main as neut_cli_main
from stock_platform_research.strategy_ab import AB_METRIC_KEYS
from stock_platform_research.strategy_ab import run_config_book
from stock_platform_research.strategy_config import StrategyConfig

#: tests only need 3 codes per industry, so groups may be small.
_INDUSTRY = {
    "000001": "银行",
    "600000": "银行",
    "600519": "银行",
    "000002": "白酒",
    "601318": "白酒",
    "300750": "白酒",
}
_TEST_PARAMS = NeutralizeParams(min_group_size=2)


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


def _suffixed(bars: pd.DataFrame) -> pd.DataFrame:
    """Engine ``daily_price`` stores ``000001.SZ``-style codes; tests join against bare."""
    out = bars.copy()
    out["code"] = out["code"] + ".SZ"
    return out


# --------------------------------------------------- default-off invariant (key)


def test_industry_column_does_not_change_the_raw_arm() -> None:
    feats = prepare_book_frame(_bars())
    with_ind = attach_industry(feats, _INDUSTRY)
    a0 = run_neutralization_book(feats, neutralize=None)
    a1 = run_neutralization_book(with_ind, neutralize=None)
    assert a0["trades"] == a1["trades"]
    assert a0["equity_curve"] == a1["equity_curve"]
    assert a0["open_positions"] == a1["open_positions"]
    assert a0["metrics"] == a1["metrics"]


def test_raw_arm_matches_the_pre_s4_baseline_book() -> None:
    feats = prepare_book_frame(_bars())
    baseline = run_config_book(feats, StrategyConfig(id="baseline", version="1"))
    raw = run_neutralization_book(feats, neutralize=None)
    assert raw["trades"] == baseline["trades"]
    assert raw["equity_curve"] == baseline["equity_curve"]
    assert raw["metrics"] == baseline["metrics"]


# ------------------------------------------------------------------- A/B contract


def test_compare_contract_and_same_definition() -> None:
    out = compare_neutralization_ab(
        prepare_book_frame(_bars()), neutralize=_TEST_PARAMS, industry_map=_INDUSTRY
    )
    assert out["ok"] is True
    assert out["replacesPicks"] is False
    assert out["liveTradingEnabled"] is False
    assert out["panelSource"] == "engine"
    assert out["industryAvailable"] is True
    assert out["nIndustries"] == 2
    assert out["sameDefinition"] == {
        "singleLoop": True,
        "singleEntryProvider": True,
        "singleMetrics": True,
        "singleExitDefinition": True,
    }
    assert set(AB_METRIC_KEYS) <= set(out["delta"])
    assert out["winner"] in {"raw", "neutral", "tie"}
    for key in ("a", "b"):
        assert "metrics" in out[key] and "review" in out[key] and "picksExposure" in out[key]
    # delta is literally neutral − raw on the shared metric block.
    assert out["delta"]["final_equity"] == pytest.approx(
        out["b"]["metrics"]["final_equity"] - out["a"]["metrics"]["final_equity"]
    )
    assert out["delta"]["n_trades"] == pytest.approx(
        out["b"]["metrics"]["n_trades"] - out["a"]["metrics"]["n_trades"]
    )
    # both arms report an exposure profile (weights sum to 1 by construction)
    for arm in ("raw", "neutral"):
        exp = out["exposure"][arm]
        assert exp["n_codes"] >= 0
        assert 0.0 <= exp["max_weight"] <= 1.0


def test_missing_industry_warns_and_degrades_gracefully() -> None:
    out = compare_neutralization_ab(
        prepare_book_frame(_bars()), neutralize=_TEST_PARAMS
    )
    assert out["industryAvailable"] is False
    assert out["nIndustries"] == 0
    assert "warning" in out
    assert out["sameDefinition"]["singleLoop"] is True


# ------------------------------------------------------------------ industry cap


def _one_session_frame() -> pd.DataFrame:
    """Four codes per industry; industry ``X`` is strictly stronger (lower vol)."""
    return pd.DataFrame(
        {
            "code": [f"X{i}" for i in range(4)] + [f"Y{i}" for i in range(4)],
            "industry": ["X"] * 4 + ["Y"] * 4,
            "close": [10.0] * 8,
            "pct_chg": [0.0] * 8,
            "ma20": [1.1] * 8,
            "ma60": [1.0] * 8,
            "vol20": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08],
            "rev_chg": [-0.1] * 8,
        }
    )


def _ctx(frame: pd.DataFrame) -> EntryContext:
    return EntryContext(
        day_index=0,
        day="2024-01-02",
        frame=frame,
        positions={},
        cash=1_000_000.0,
        equity=1_000_000.0,
        last_exit_idx={},
        params=ReplayParams(),
    )


def test_max_per_industry_caps_single_industry_dominance() -> None:
    frame = _one_session_frame()
    gate = EntryGateParams(vol_filter=False)  # keep the vol spread out of the gate
    base = screener_entry_provider(
        min_pick_score=0.0, gate_params=gate, max_per_industry=None
    )(_ctx(frame))
    capped = screener_entry_provider(
        min_pick_score=0.0, gate_params=gate, max_per_industry=1
    )(_ctx(frame))
    assert len(base) == 8  # uncapped: every eligible code, X first
    assert len(capped) == 2  # one per industry
    assert {p["code"][0] for p in capped} == {"X", "Y"}
    # the cap keeps the *best* of each industry and preserves composite order
    assert capped[0]["code"] == "X0"
    assert capped[1]["code"] == "Y0"


# ------------------------------------------------------------ from-bars / loader


def test_from_bars_end_to_end_and_fail_closed() -> None:
    bars = _bars()
    out = neutralization_ab_from_bars(
        bars, neutralize=_TEST_PARAMS, industry_map=_INDUSTRY
    )
    assert out["ok"] is True
    assert out["universe"] == "stock"
    assert out["industryAvailable"] is True
    assert all(out["sameDefinition"].values())

    empty = neutralization_ab_from_bars(
        bars.iloc[0:0], neutralize=_TEST_PARAMS, industry_map=_INDUSTRY
    )
    assert empty["ok"] is False
    assert empty["reason"] == "no bars in range"
    assert empty["liveTradingEnabled"] is False


def _make_market_db(tmp_path, bars: pd.DataFrame, *, with_fundamentals: bool = True):
    db = tmp_path / "market.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL)")
    con.execute("CREATE INDEX idx_dp_date ON daily_price (date)")
    con.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?)",
        list(bars[["code", "date", "close", "pct_chg"]].itertuples(index=False, name=None)),
    )
    if with_fundamentals:
        con.execute("CREATE TABLE fundamentals (code TEXT, name TEXT, industry TEXT)")
        con.executemany(
            "INSERT INTO fundamentals VALUES (?,?,?)",
            [(k, k, v) for k, v in _INDUSTRY.items()],
        )
    con.commit()
    con.close()
    return db


def test_load_engine_industry_reads_codes_and_is_read_only(tmp_path) -> None:
    db = _make_market_db(tmp_path, _suffixed(_bars()))
    before = db.read_bytes()
    mapping = load_engine_industry(db)
    assert mapping["000001"] == "银行" and mapping["300750"] == "白酒"
    assert db.read_bytes() == before  # read-only


def test_load_engine_industry_fails_closed_without_table(tmp_path) -> None:
    db = _make_market_db(tmp_path, _suffixed(_bars()), with_fundamentals=False)
    with pytest.raises(KeyError):
        load_engine_industry(db)


def test_cli_end_to_end_json(tmp_path, capsys) -> None:
    db = _make_market_db(tmp_path, _suffixed(_bars()))
    code = neut_cli_main(
        [
            "--db",
            str(db),
            "--start",
            "2024-01-01",
            "--end",
            "2024-12-31",
            "--mode",
            "demean",
            "--min-group-size",
            "2",
            "--json",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "industry neutralization A/B" in out
    assert "winner=" in out
    # the final JSON line is the full report
    payload = out.strip().splitlines()[-1]
    import json

    report = json.loads(payload)
    assert report["ok"] is True
    assert report["industryAvailable"] is True
    assert report["nIndustries"] == 2


def test_cli_requires_a_db(monkeypatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_ENGINE_MARKET_DB", raising=False)
    with pytest.raises(SystemExit):
        neut_cli_main(["--db", ""])
