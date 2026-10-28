"""Quote-date OHLC cache. No live network."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import stock_platform_research.quotes as quotes
from stock_platform_research.quotes import load_ohlc, resolve_prev_close, resolve_quote_date


def test_cache_hit_does_not_fetch(tmp_path: Path):
    day = "2026-10-28"
    blob = {
        "asof": day,
        "rows": {"600519": {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}},
        "count": 1,
    }
    (tmp_path / f"ohlc-{day}.json").write_text(json.dumps(blob), encoding="utf-8")

    def _boom(symbols, asof):
        raise AssertionError("fetch must not run on a full cache hit")

    rows, err = load_ohlc(["600519"], day, cache_dir=tmp_path, allow_network=True, fetch=_boom)
    assert err is None
    assert rows["600519"]["close"] == 1.5


def test_source_failure_returns_empty_dict(tmp_path: Path):
    def _fail(symbols, asof):
        return {}, "down"

    rows, err = load_ohlc(["600000"], "2026-10-28", cache_dir=tmp_path, allow_network=True, fetch=_fail)
    assert rows == {}
    assert err


def test_cache_write_keeps_a6_keys(tmp_path: Path):
    def _fetch(symbols, asof):
        return {
            "600000": {"open": 1, "high": 2, "low": 0.5, "close": 1.2, "extra": 9},
        }, None

    load_ohlc(["600000"], "2026-10-28", cache_dir=tmp_path, allow_network=True, fetch=_fetch)
    blob = json.loads((tmp_path / "ohlc-2026-10-28.json").read_text(encoding="utf-8"))
    assert set(blob) == {"asof", "rows", "count"}
    assert set(blob["rows"]["600000"]) == {"open", "high", "low", "close"}


def test_quote_date_equal_asof_does_not_use_asof_close_as_prev():
    prev = resolve_prev_close(
        quote_date="2026-10-09",
        asof="2026-10-09",
        asof_close=100.0,
        prior_close=80.0,
    )
    assert prev == 80.0
    assert prev != 100.0


def test_weekend_run_date_falls_back(monkeypatch):
    class _Cal:
        def is_trading_day(self, d):
            return d.weekday() < 5

        def last_trading_day(self, d):
            while d.weekday() >= 5:
                d = date.fromordinal(d.toordinal() - 1)
            return d

    monkeypatch.setattr(
        "stock_platform_providers.get_trading_calendar",
        lambda market: _Cal(),
        raising=False,
    )
    # Saturday 2026-10-24 → Friday 2026-10-23, without reading the holiday table.
    # The lazy import is patched on the providers module before the call.
    import stock_platform_providers

    monkeypatch.setattr(stock_platform_providers, "get_trading_calendar", lambda market: _Cal())
    assert resolve_quote_date(date(2026, 10, 24)) == date(2026, 10, 23)


def test_quotes_module_has_no_top_level_providers_import():
    text = Path(quotes.__file__).read_text(encoding="utf-8")
    hits = [line for line in text.splitlines() if "stock_platform_providers" in line]
    assert hits
    assert all(line[:1].isspace() for line in hits)
