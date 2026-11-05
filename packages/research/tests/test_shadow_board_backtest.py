"""Shadow Final Board walk-forward backtest — same engine as lvrev, PIT, fail-closed."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_platform_research.book_replay import ReplayParams
from stock_platform_research.shadow_board.backtest import (
    compare_shadow_vs_lvrev,
    frame_to_universe,
    prepare_shadow_frame,
    render_shadow_backtest_markdown,
    run_shadow_book,
    shadow_board_for_frame,
)

N_CODES = 24
N_DAYS = 140


def _bars(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=N_DAYS)
    rows = []
    for i in range(N_CODES):
        code = f"{600000 + i:06d}.SH"
        px = 10.0 + i
        for d in days:
            pct = float(rng.normal(0.05, 1.8))
            pct = max(min(pct, 9.0), -9.0)
            px *= 1.0 + pct / 100.0
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": round(px, 3),
                    "pct_chg": round(pct, 4),
                    "amount": 5e7 if i % 6 else 5e6,  # every 6th code illiquid
                }
            )
    return pd.DataFrame(rows)


def _names(st_codes: tuple[int, ...] = ()) -> dict[str, str]:
    out = {}
    for i in range(N_CODES):
        code = f"{600000 + i:06d}"
        out[code] = f"*ST样本{i}" if i in st_codes else f"样本{i}"
    return out


def _industry() -> dict[str, str]:
    return {f"{600000 + i:06d}": f"行业{i % 4}" for i in range(N_CODES)}


def test_frame_to_universe_drops_illiquid_and_keeps_missing_name_empty() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    day = feats[feats["trade_date"] == feats["trade_date"].max()]
    uni = frame_to_universe(day, name_map={"600001": "样本1"})
    codes = {r["code"] for r in uni}
    assert "600000" not in codes  # amount 5e6 < AMOUNT_MIN
    by = {r["code"]: r for r in uni}
    assert by["600001"]["name"] == "样本1"
    assert by["600002"]["name"] == ""  # fail-closed: secondary_pick rejects
    assert "rs20" in by["600001"] and "industry" in by["600001"]


def test_no_name_map_means_quality_and_short_pools_empty() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    day = feats[feats["trade_date"] == feats["trade_date"].max()]
    res = shadow_board_for_frame(day, day="2025-07-01", name_map=None)
    assert res["schools"]["S3"]["candidates"] == []
    assert res["schools"]["S4"]["candidates"] == []
    assert res["schools"]["S2"]["status"] == "empty"  # no historical DI


def test_st_names_never_reach_final_board() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    st = (1, 2, 3, 4, 5)
    names = _names(st_codes=st)
    st_codes = {f"{600000 + i:06d}" for i in st}
    for _, day in list(feats.groupby("trade_date"))[-20:]:
        res = shadow_board_for_frame(day, day="x", name_map=names)
        passed = {r["code"] for r in res["round2"]["passed"]}
        assert not (passed & st_codes)


def test_board_is_pit_truncating_future_bars_changes_nothing() -> None:
    bars = _bars()
    cut = sorted(bars["date"].unique())[100]
    full = prepare_shadow_frame(bars, industry_map=_industry())
    trunc = prepare_shadow_frame(bars[bars["date"] <= cut], industry_map=_industry())
    ts = pd.Timestamp(cut)
    a = shadow_board_for_frame(full[full["trade_date"] == ts], day=cut, name_map=_names())
    b = shadow_board_for_frame(trunc[trunc["trade_date"] == ts], day=cut, name_map=_names())
    assert a["round2"]["passed"] == b["round2"]["passed"]


def test_compare_runs_both_arms_through_same_engine() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    params = ReplayParams(initial_capital=100000.0, max_positions=5)
    out = compare_shadow_vs_lvrev(feats, name_map=_names(), params=params)
    assert out["ok"] is True
    assert out["sameEngine"] is True
    assert out["excludedFromPerformance"] is True
    assert out["replacesPicks"] is False
    assert out["liveTradingEnabled"] is False
    for arm in ("lvrev", "shadow"):
        assert "sharpe" in out[arm]["metrics"]
        assert out[arm]["excessReturn"] is None  # no index → not fabricated
    sh = out["shadow"]["shadow"]
    assert sh["evaluatedDays"] > 0
    assert 0.0 <= sh["emptyBoardRatio"] <= 1.0
    assert sh["schoolCoverage"]["S2"]["seats"] == 0
    assert set(out["delta"]) >= {"sharpe", "total_return", "max_drawdown"}
    md = render_shadow_backtest_markdown(out)
    assert "影子终榜" in md and "空榜比例" in md


def test_shadow_book_respects_engine_position_cap() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    out = run_shadow_book(
        feats, name_map=_names(), params=ReplayParams(initial_capital=100000.0, max_positions=3)
    )
    assert max((p["n_positions"] for p in out["equityCurve"]), default=0) <= 3


def test_index_close_yields_excess_return() -> None:
    feats = prepare_shadow_frame(_bars(), industry_map=_industry())
    dates = sorted({d.date().isoformat() for d in feats["trade_date"]})
    index_close = {d: 100.0 + i * 0.1 for i, d in enumerate(dates)}
    out = compare_shadow_vs_lvrev(feats, name_map=_names(), index_close=index_close)
    assert out["lvrev"]["benchmarkReturn"] is not None
    assert out["shadow"]["excessReturn"] is not None


def test_empty_frame_fail_closed() -> None:
    out = compare_shadow_vs_lvrev(pd.DataFrame())
    assert out["ok"] is False
    assert "无可用数据" in render_shadow_backtest_markdown(out)


def test_cli_backtest_missing_db_is_fail_closed(tmp_path, capsys) -> None:
    from stock_platform_research.shadow_board.cli import main

    rc = main(["--backtest", "--db", str(tmp_path / "nope.db"), "--bt-out-dir", str(tmp_path / "bt")])
    assert rc == 2
    assert not (tmp_path / "bt").exists()
    assert "market.db" in capsys.readouterr().err
