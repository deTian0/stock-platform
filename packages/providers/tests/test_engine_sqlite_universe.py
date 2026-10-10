"""X1: whole-market symbol enumeration from the engine market.db (read-only).

The query + coverage rules live **here** (providers) and nowhere else; the
research side only filters by asset class. These tests pin that contract with a
synthetic warehouse, so CI never needs the 3.14 GB real file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from stock_platform_providers.engine_sqlite import EngineSqliteProvider

ASOF = "2026-09-08"

# Window for asof=2026-09-08 with the default 120-day lookback: 2026-05-11 …
_BARS: list[tuple[str, str]] = [
    # 5 bars with the modern suffix + 1 legacy bare row = 6 after collapsing
    ("600519.SH", "2026-09-01"),
    ("600519.SH", "2026-09-02"),
    ("600519.SH", "2026-09-03"),
    ("600519.SH", "2026-09-04"),
    ("600519.SH", "2026-09-05"),
    ("600519", "2026-09-06"),  # legacy bare form of the same code
    ("000001.SZ", "2026-09-01"),
    ("000001.SZ", "2026-09-08"),  # keeps MAX(date) == ASOF
    # ETF — providers deliberately do NOT filter these (asset class is B4's job)
    ("510300.SH", "2026-09-01"),
    ("510300.SH", "2026-09-02"),
    ("510300.SH", "2026-09-03"),
    ("510300.SH", "2026-09-04"),
    # BSE — excluded by default through symbol.is_bse_symbol
    ("830001.BJ", "2026-09-01"),
    ("830001.BJ", "2026-09-02"),
    ("830001.BJ", "2026-09-03"),
    ("920002.BJ", "2026-09-01"),
    # Dirty leftovers that are not 6-digit A-share codes
    ("42", "2026-09-01"),
    ("8", "2026-09-01"),
    # Outside the window — must not resurrect anything
    ("600519.SH", "2020-01-02"),
]


def _make_db(path: Path, bars: list[tuple[str, str]] | None = None) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE daily_price (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            PRIMARY KEY (code, date)
        )
        """
    )
    conn.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
        [(c, d, 10.0, 0.0, 100.0, 1e4) for c, d in (bars if bars is not None else _BARS)],
    )
    conn.commit()
    conn.close()
    return path


def test_list_symbols_excludes_bse_and_dirty_codes(tmp_path: Path) -> None:
    provider = EngineSqliteProvider(_make_db(tmp_path / "market.db"))
    assert provider.list_symbols(asof=ASOF) == ["000001", "510300", "600519"]


def test_list_symbols_can_include_bse(tmp_path: Path) -> None:
    provider = EngineSqliteProvider(_make_db(tmp_path / "market.db"))
    out = provider.list_symbols(asof=ASOF, include_bse=True)
    assert out == ["000001", "510300", "600519", "830001", "920002"]


def test_list_symbols_collapses_bare_and_suffixed_forms(tmp_path: Path) -> None:
    """600519.SH (5 bars) + bare 600519 (1 bar) must count as one 6-bar code."""
    provider = EngineSqliteProvider(_make_db(tmp_path / "market.db"))
    assert provider.list_symbols(asof=ASOF, min_bars=6) == ["600519"]
    assert provider.list_symbols(asof=ASOF, min_bars=4) == ["510300", "600519"]


def test_list_symbols_honours_window_and_limit(tmp_path: Path) -> None:
    provider = EngineSqliteProvider(_make_db(tmp_path / "market.db"))
    # asof before the September bars → window contains only the 2020 row
    assert provider.list_symbols(asof="2020-01-05", lookback_days=30) == ["600519"]
    assert provider.list_symbols(asof=ASOF, limit=2) == ["000001", "510300"]


def test_list_symbols_defaults_to_latest_trade_date(tmp_path: Path) -> None:
    provider = EngineSqliteProvider(_make_db(tmp_path / "market.db"))
    assert provider.latest_trade_date() == ASOF
    assert provider.list_symbols() == ["000001", "510300", "600519"]


def test_list_symbols_empty_warehouse_is_empty_list(tmp_path: Path) -> None:
    """Empty is returned (not raised) here — fail-closed is the caller's job."""
    provider = EngineSqliteProvider(_make_db(tmp_path / "market.db", bars=[]))
    assert provider.latest_trade_date() is None
    assert provider.list_symbols() == []


def test_list_symbols_rejects_missing_db(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        EngineSqliteProvider(tmp_path / "nope.db")
