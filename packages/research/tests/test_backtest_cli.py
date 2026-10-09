"""Tests for the backtest CLI data path: the read-only ``market.db`` loader.

``load_engine_bars`` is the single entry point to the 3.1 GB engine DB, and its
strategy was changed on 2026-10-09 from a ``WHERE date BETWEEN`` scan (54.9 s)
to a plain full-table stream plus in-memory filter (12.5 s). These tests pin the
filter/sort/read-only semantics so a future "optimisation" cannot silently
change which rows the backtest sees.
"""

from __future__ import annotations

import sqlite3

import pytest

from stock_platform_research.backtest_cli import (
    build_parser,
    filter_universe,
    load_engine_bars,
    main,
)
from stock_platform_research.portfolio import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_STAMP_SELL_RATE,
)

ROWS = [
    ("600519.SH", "2023-01-03", 10.0, 0.01),
    ("600519.SH", "2023-01-04", 11.0, 0.10),
    ("000001.SZ", "2023-01-03", 5.0, -0.02),
    ("000001.SZ", "2023-01-04", 5.5, 0.10),
    ("830799.BJ", "2023-01-03", 7.0, 0.0),
    ("430047.BJ", "2023-01-04", 3.0, 0.0),
]


def _make_db(tmp_path, rows=ROWS):
    db = tmp_path / "market.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL)")
    con.execute("CREATE INDEX idx_dp_date ON daily_price (date)")
    con.executemany("INSERT INTO daily_price VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()
    return db


def test_loader_returns_all_rows_with_expected_columns(tmp_path):
    df = load_engine_bars(_make_db(tmp_path))
    assert list(df.columns) == ["code", "date", "close", "pct_chg"]
    assert len(df) == len(ROWS)


def test_loader_filters_inclusive_date_window(tmp_path):
    df = load_engine_bars(_make_db(tmp_path), start="2023-01-04", end="2023-01-04")
    assert set(df["date"]) == {"2023-01-04"}
    assert len(df) == 3


def test_loader_filters_codes(tmp_path):
    df = load_engine_bars(_make_db(tmp_path), codes=["600519.SH"])
    assert set(df["code"]) == {"600519.SH"}
    assert len(df) == 2


def test_loader_sorts_by_code_then_date(tmp_path):
    df = load_engine_bars(_make_db(tmp_path))
    assert df["code"].tolist() == [
        "000001.SZ", "000001.SZ", "430047.BJ", "600519.SH", "600519.SH", "830799.BJ",
    ]
    assert df["date"].tolist() == [
        "2023-01-03", "2023-01-04", "2023-01-04", "2023-01-03", "2023-01-04", "2023-01-03",
    ]


def test_loader_does_not_write_to_db(tmp_path):
    db = _make_db(tmp_path)
    before = db.read_bytes()
    load_engine_bars(db)
    assert db.read_bytes() == before


def test_filter_universe_drops_bse(tmp_path):
    df = filter_universe(load_engine_bars(_make_db(tmp_path)))
    assert set(df["code"]) == {"600519.SH", "000001.SZ"}


def test_filter_universe_keeps_bse_when_disabled(tmp_path):
    df = filter_universe(load_engine_bars(_make_db(tmp_path)), exclude_bse=False)
    assert "830799.BJ" in set(df["code"])


def test_missing_db_raises(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        load_engine_bars(tmp_path / "nope.db")


# ---------- B3: cost flags ----------

def test_parser_defaults_match_cost_model_constants():
    args = build_parser().parse_args([])
    assert args.commission_rate == DEFAULT_COMMISSION_RATE
    assert args.stamp_sell_rate == DEFAULT_STAMP_SELL_RATE
    assert args.slippage_bps == 0.0
    assert args.zero_cost is False


def test_parser_accepts_cost_flags():
    args = build_parser().parse_args(
        ["--commission-rate", "0.001", "--stamp-sell-rate", "0.0008", "--slippage-bps", "10"]
    )
    assert args.commission_rate == 0.001
    assert args.stamp_sell_rate == 0.0008
    assert args.slippage_bps == 10.0


def test_cli_zero_cost_forces_every_rate_to_zero(tmp_path, capsys):
    db = _make_db(tmp_path)
    rc = main(
        ["--db", str(db), "--zero-cost", "--start", "2023-01-03", "--end", "2023-01-04"]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "[cost]" in err
    assert "commission=0" in err
    assert "stamp_sell=0" in err
    assert "slippage_bps=0" in err


# ---------- B4: universe flag ----------

def test_parser_universe_defaults_to_stock():
    args = build_parser().parse_args([])
    assert args.universe == "stock"


def test_parser_accepts_universe_choices():
    for u in ("stock", "etf", "all"):
        assert build_parser().parse_args(["--universe", u]).universe == u


def test_parser_rejects_unknown_universe():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--universe", "bogus"])


def test_cli_echoes_universe(tmp_path, capsys):
    db = _make_db(tmp_path)
    rc = main(
        ["--db", str(db), "--universe", "all", "--start", "2023-01-03", "--end", "2023-01-04"]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "[universe] all" in err
