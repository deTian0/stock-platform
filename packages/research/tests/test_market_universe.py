"""X1: market-wide universe resolution (research side) — filters + fail-closed.

The DB query lives in ``providers.engine_sqlite.list_symbols`` and is tested
there against a synthetic warehouse. This module pins the *research* half:
asset-class filtering (reusing the B4 single definition), provenance, cost
measurement, and the one entry point :func:`resolve_universe`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from stock_platform_research.daily_pipeline import run_daily_pipeline
from stock_platform_research.market_universe import (
    ASSET_TYPE_CHOICES,
    MarketUniverse,
    resolve_market_universe,
    resolve_universe,
)
from stock_platform_research.market_universe_cli import main as cli_main
from stock_platform_research.portfolio import asset_class
from stock_platform_research.universe import (
    UNIVERSE_SOURCES,
    UniverseEmptyError,
    default_universe_fixture_path,
    load_universe,
)

# stock / stock / etf / fund(LOF) — one per classification branch. BSE codes are
# deliberately absent: excluding them is the *provider's* job (see
# test_engine_sqlite_universe.py), so a source that hands them over is trusted.
MIXED_CODES = ["600519", "000001", "510300", "161725"]


class FakeMarketSource:
    """Stands in for ``EngineSqliteProvider.list_symbols``."""

    def __init__(self, codes: list[str]) -> None:
        self._codes = list(codes)
        self.calls: list[dict[str, Any]] = []

    def list_symbols(
        self,
        *,
        asof: Any = None,
        lookback_days: int = 120,
        min_bars: int = 1,
        include_bse: bool = False,
        limit: int | None = None,
    ) -> list[str]:
        self.calls.append(
            {
                "asof": asof,
                "lookback_days": lookback_days,
                "min_bars": min_bars,
                "include_bse": include_bse,
                "limit": limit,
            }
        )
        return list(self._codes)


def test_asset_filter_uses_the_b4_single_definition() -> None:
    src = FakeMarketSource(MIXED_CODES)
    for key in ASSET_TYPE_CHOICES:
        universe = resolve_market_universe(src, asset_type=key)
        if key == "all":
            expected = list(MIXED_CODES)
        else:
            expected = [c for c in MIXED_CODES if asset_class(c) == key]
        assert list(universe.symbols) == expected, key
    # The classifier itself is imported, never re-implemented here.
    assert asset_class("510300") == "etf"
    assert asset_class("161725") == "fund"


def test_counts_and_provenance_are_reported() -> None:
    universe = resolve_market_universe(
        FakeMarketSource(MIXED_CODES), asof="2026-09-08", min_bars=5, measure_memory=True
    )
    assert isinstance(universe, MarketUniverse)
    assert universe.counts["source"] == len(MIXED_CODES)
    assert universe.counts["final"] == 2  # stock only
    assert universe.asof == "2026-09-08"
    assert universe.elapsed_s >= 0.0
    assert universe.peak_memory_mb is not None
    payload = universe.to_dict()
    assert payload["symbol_count"] == len(universe.symbols)
    assert json.loads(json.dumps(payload))["asset_type"] == "stock"


def test_limit_is_applied_after_filtering() -> None:
    # Order follows the source (providers already return sorted codes); research
    # never re-sorts, so provenance stays traceable.
    universe = resolve_market_universe(FakeMarketSource(MIXED_CODES), limit=1)
    assert list(universe.symbols) == ["600519"]
    assert universe.limit == 1


def test_bse_exclusion_belongs_to_the_provider_side() -> None:
    """Research trusts the source: no BSE rule is duplicated here.

    ``830001`` classifies as ``stock`` under :func:`portfolio.asset_class`, so it
    survives — the guarantee comes from
    ``EngineSqliteProvider.list_symbols(include_bse=False)``, which is tested
    against a synthetic warehouse in the providers package.
    """
    universe = resolve_market_universe(FakeMarketSource(["600519", "830001"]))
    assert list(universe.symbols) == ["600519", "830001"]


def test_empty_universe_fails_closed() -> None:
    with pytest.raises(UniverseEmptyError) as exc:
        resolve_market_universe(FakeMarketSource([]))
    assert "全市场宇宙解析结果为空" in str(exc.value)


def test_missing_source_fails_closed() -> None:
    for bad in (None, object()):
        with pytest.raises(UniverseEmptyError) as exc:
            resolve_market_universe(bad)
        assert "market_db 宇宙需要注入行情源" in str(exc.value)


def test_unknown_asset_type_fails_closed() -> None:
    with pytest.raises(UniverseEmptyError) as exc:
        resolve_market_universe(FakeMarketSource(MIXED_CODES), asset_type="bond")
    assert "unknown asset_type" in str(exc.value)


def test_resolve_universe_dispatches_by_source() -> None:
    assert UNIVERSE_SOURCES == ("config", "market_db")

    fixture = default_universe_fixture_path()
    assert resolve_universe(source="config", path=fixture) == load_universe(fixture)

    src = FakeMarketSource(["600519", "000001"])
    assert resolve_universe(source="market_db", market_symbol_source=src) == [
        "600519",
        "000001",
    ]
    # Explicit symbols win over both sources (pre-X1 behaviour preserved).
    assert resolve_universe(
        source="market_db", market_symbol_source=src, symbols=["300750"]
    ) == ["300750"]

    with pytest.raises(UniverseEmptyError) as exc:
        resolve_universe(source="spreadsheet", path=fixture)
    assert "unknown universe source" in str(exc.value)


# --- pipeline wiring (X1 end-to-end, still zero network) ---


def _synth_bars(symbol: str, asof: date, n: int = 70, base: float = 10.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    closes: list[tuple[date, float]] = []
    day = asof
    while len(closes) < n:
        if day.weekday() < 5:
            idx = n - len(closes)
            closes.append((day, base + 0.02 * idx))
        day -= timedelta(days=1)
    closes.reverse()
    for d, px in closes:
        rows.append(
            {
                "symbol": symbol,
                "date": d.isoformat(),
                "open": px * 0.99,
                "high": px * 1.01,
                "low": px * 0.98,
                "close": px,
                "volume": 1_000_000,
                "amount": px * 1_000_000,
            }
        )
    return rows


class _FakeDailyProvider:
    def __init__(self, by_sym: dict[str, list[dict[str, Any]]]) -> None:
        self.by_sym = by_sym

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        out = []
        for sym in symbols:
            for row in self.by_sym.get(sym, []):
                d = date.fromisoformat(str(row["date"])[:10])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                out.append(row)
        return out


def test_daily_pipeline_market_db_universe(tmp_path: Path) -> None:
    asof = date(2026, 9, 2)
    codes = ["600519", "000001"]
    provider = _FakeDailyProvider({c: _synth_bars(c, asof) for c in codes})
    market = FakeMarketSource(codes + ["510300"])  # ETF dropped by asset_type=stock

    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        universe_source="market_db",
        market_symbol_source=market,
        market_universe_kwargs={"asset_type": "stock", "min_bars": 1},
        skip_refresh=True,
        top_n=2,
        persist_db=False,
    )
    assert report.ok, report.error
    assert report.universe is not None
    assert report.universe["source"] == "market_db"
    assert report.universe["size"] == 2
    # The pipeline injects its own asof / window into the market query.
    assert market.calls[0]["asof"] == asof
    assert market.calls[0]["lookback_days"] == 120


def test_daily_pipeline_market_db_without_source_fails_closed(tmp_path: Path) -> None:
    report = run_daily_pipeline(
        asof="2026-09-02",
        provider=_FakeDailyProvider({}),
        out_dir=tmp_path,
        universe_source="market_db",
        market_symbol_source=None,
        skip_refresh=True,
        persist_db=False,
    )
    assert not report.ok
    assert report.universe is not None
    assert report.universe["source"] == "market_db"
    assert "market_db 宇宙需要注入行情源" in (report.error or "")


# --- CLI ---


def _make_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, "
        "pct_chg REAL, vol REAL, amount REAL)"
    )
    conn.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?,?,?)",
        [
            ("600519.SH", "2026-09-01", 10.0, 0.0, 1.0, 1.0),
            ("000001.SZ", "2026-09-01", 10.0, 0.0, 1.0, 1.0),
            ("510300.SH", "2026-09-01", 10.0, 0.0, 1.0, 1.0),
            ("830001.BJ", "2026-09-01", 10.0, 0.0, 1.0, 1.0),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_cli_requires_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_ENGINE_MARKET_DB", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli_main([])
    assert "market.db" in str(exc.value)


def test_cli_reports_measured_numbers(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = _make_db(tmp_path / "market.db")
    assert cli_main(["--db", str(db), "--asof", "2026-09-08", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol_count"] == 2  # stock only: 000001 / 600519
    assert payload["counts"]["source"] == 3  # BSE dropped by the provider
    assert payload["elapsed_s"] >= 0.0
    assert payload["db"]["size_gb"] is not None

    assert cli_main(["--db", str(db), "--asset-type", "all", "--symbols-only"]) == 0
    assert capsys.readouterr().out.split() == ["000001", "510300", "600519"]
