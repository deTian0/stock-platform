"""中文名 plumbing: picks / boards / digest (decorative, never load-bearing).

The contract these tests lock down: attaching a name map may only ADD a ``name``
string where a name is actually known. Without a map — or for a code the map does
not cover — the brief is byte-identical to the pre-name behaviour, so no existing
consumer (performance log, picks ledger, hit cycle) can drift.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from stock_platform_research.backtest_cli import load_engine_names
from stock_platform_research.brief import build_premarket_brief

_NAMES = {"600519": "贵州茅台", "000001": "平安银行", "000002": "万科A"}


def _panel() -> pd.DataFrame:
    """Uniform features so every row clears the entry gates and survives to picks.

    Values are copied from the known entry-passing row in
    ``test_universe_reasons._panel`` (low vol20, negative rev_chg, ma20 > ma60).
    """
    return pd.DataFrame(
        {
            "trade_date": ["2026-09-02"] * 4,
            "symbol": ["600519.SH", "000001.SZ", "000002.SZ", "000004.SZ"],
            "open": [10, 10, 10, 10],
            "close": [10.5, 10.1, 9.9, 10.2],
            "vol20": [0.10, 0.10, 0.10, 0.10],
            "rev_chg": [-0.08, -0.08, -0.08, -0.08],
            "ma20": [10.0, 10.0, 10.0, 10.0],
            "ma60": [9.0, 9.0, 9.0, 9.0],
            "trend_up": [True, True, True, True],
            "rs20": [5.0, 3.0, 1.0, 2.0],
        }
    )


def test_brief_attaches_names_to_picks_and_boards() -> None:
    brief = build_premarket_brief(
        asof="2026-09-02", panel=_panel(), top_n=4, name_map=_NAMES
    )
    by_symbol = {p["symbol"]: p for p in brief["picks"]}
    assert len(by_symbol) == 4
    for symbol, pick in by_symbol.items():
        expected = _NAMES.get(symbol[:6])
        if expected:
            assert pick["name"] == expected
        else:
            # A code the map does not cover carries no name key at all.
            assert "name" not in pick

    items = {i["symbol"]: i for i in brief["rankings"]["boards"]["quality"]["items"]}
    assert items["600519.SH"]["name"] == "贵州茅台"
    assert "name" not in items["000004.SZ"]


def test_brief_without_name_map_is_unchanged() -> None:
    """No map -> no ``name`` key anywhere (byte-level contract preserved)."""
    brief = build_premarket_brief(asof="2026-09-02", panel=_panel(), top_n=4)
    assert brief["picks"]
    assert all("name" not in p for p in brief["picks"])
    items = brief["rankings"]["boards"]["quality"]["items"]
    assert all("name" not in i for i in items)


def test_brief_only_adds_names_for_known_codes() -> None:
    brief = build_premarket_brief(
        asof="2026-09-02", panel=_panel(), top_n=4, name_map={"000004": "国华网安"}
    )
    by_symbol = {p["symbol"]: p for p in brief["picks"]}
    assert by_symbol["000004.SZ"]["name"] == "国华网安"
    assert "name" not in by_symbol["600519.SH"]


def test_digest_picks_table_renders_the_name(tmp_path: Path, monkeypatch) -> None:
    from stock_platform_research.daily_digest import build_digest_text
    from stock_platform_research.persistence import (
        open_brief_repository,
        reset_brief_repository_cache,
    )

    # ``monkeypatch`` (not raw os.environ) so the session-level guard installed by
    # the repo-root conftest is RESTORED, not dropped — dropping it would make
    # every later test fall back to the repo ``data/`` dir (ADR 0069).
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'b.db').as_posix()}")
    reset_brief_repository_cache()
    try:
        brief = build_premarket_brief(
            asof="2026-09-02", panel=_panel(), top_n=2, name_map=_NAMES
        )
        record = open_brief_repository().save(brief, symbols=list(_NAMES))
        text = build_digest_text(record, hits_repo=None)
        assert "| # | 代码 | 名称 | 综合分 | 收盘(asof) |" in text
        assert "贵州茅台" in text
    finally:
        reset_brief_repository_cache()


def test_load_engine_names_is_fail_open(tmp_path: Path) -> None:
    """A DB without ``fundamentals`` yields ``{}`` — a name is never load-bearing."""
    db = tmp_path / "no_names.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL)")
    con.commit()
    con.close()
    assert load_engine_names(db) == {}


def test_load_engine_names_reads_fundamentals(tmp_path: Path) -> None:
    db = tmp_path / "names.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE fundamentals (code TEXT, name TEXT, industry TEXT)")
    con.executemany(
        "INSERT INTO fundamentals VALUES (?,?,?)",
        [("600519", "贵州茅台", "白酒"), ("000001", "平安银行", "银行")],
    )
    con.commit()
    con.close()
    assert load_engine_names(db) == {"600519": "贵州茅台", "000001": "平安银行"}
