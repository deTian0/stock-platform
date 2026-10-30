"""Quote-date OHLC cache. No live network."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import stock_platform_research.quotes as quotes
from stock_platform_research.quotes import load_ohlc, resolve_prev_close, resolve_quote_date


@pytest.fixture(autouse=True)
def _no_network_snapshot(monkeypatch):
    """`_fetch_ohlc` 的第二源兜底默认打桩：单测绝不联网。"""
    from stock_platform_research import day_quote_cli as dq

    monkeypatch.setattr(dq, "_snapshot_fill", lambda symbols, asof: ({}, "stub 快照不可用"))


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


def test_fetch_ohlc_keeps_successful_chunks(monkeypatch):
    """整批一个请求会被断路器整体抛出；分批后单批失败只损失该批。"""
    from stock_platform_research import day_quote_cli as dq

    def _fake_chunk(symbols, start, end):
        if symbols[0] == "600000":  # 该批永远失败
            raise ConnectionError("eastmoney circuit open")
        return [
            {
                "symbol": symbols[0],
                "date": "2026-10-29",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
            }
        ]

    monkeypatch.setattr(dq, "_fetch_ohlc_chunk", _fake_chunk)
    monkeypatch.setattr(dq, "CHUNK_SIZE", 2)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    rows, err = dq._fetch_ohlc(["600000", "600001", "600002", "600003"], "2026-10-29")

    assert "600000" not in rows  # 该批全失败
    assert rows["600002"]["close"] == 1.5  # 其它批照常落库
    assert rows["600003"]["close"] == 1.5  # 逐轮补齐把漏掉的补回来
    assert err and "部分缺失" in err


def test_fetch_ohlc_reports_total_failure(monkeypatch):
    from stock_platform_research import day_quote_cli as dq

    def _always_fail(symbols, start, end):
        raise ConnectionError("down")

    monkeypatch.setattr(dq, "_fetch_ohlc_chunk", _always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    rows, err = dq._fetch_ohlc(["600000"], "2026-10-29")
    assert rows == {}
    assert err and "东财不可达" in err and "快照亦不可用" in err


def test_fetch_ohlc_falls_back_to_snapshot_when_eastmoney_is_dead(monkeypatch):
    """东财整体不可达（CircuitOpenError）时，必须换腾讯/新浪快照，三列不能全空。"""
    from stock_platform_research import day_quote_cli as dq

    def _dead(symbols, start, end):
        raise ConnectionError("eastmoney circuit open")

    monkeypatch.setattr(dq, "_fetch_ohlc_chunk", _dead)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(
        dq,
        "_snapshot_fill",
        lambda symbols, asof: (
            {s: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5} for s in symbols},
            None,
        ),
    )

    rows, err = dq._fetch_ohlc(["600000", "600001"], "2026-10-30")
    assert set(rows) == {"600000", "600001"}
    assert rows["600000"]["open"] == 1.0
    assert err and "快照" in err  # 换源要留痕，不能静默


def test_fetch_ohlc_only_asks_snapshot_for_the_gap(monkeypatch):
    from stock_platform_research import day_quote_cli as dq

    def _partial(symbols, start, end):
        return [
            {"symbol": s, "date": "2026-10-30", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}
            for s in symbols
            if s == "600000"
        ]

    asked: list[list[str]] = []

    def _snap(symbols, asof):
        asked.append(list(symbols))
        return {s: {"open": 9.0, "high": 9.5, "low": 8.5, "close": 9.2} for s in symbols}, None

    monkeypatch.setattr(dq, "_fetch_ohlc_chunk", _partial)
    monkeypatch.setattr(dq, "_snapshot_fill", _snap)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    rows, err = dq._fetch_ohlc(["600000", "600001"], "2026-10-30")
    assert rows["600000"]["close"] == 1.5  # 东财优先，不被快照覆盖
    assert rows["600001"]["close"] == 9.2  # 缺口由快照补
    assert asked == [["600001"]]
    assert err is None


def test_fetch_ohlc_snapshot_exception_does_not_escape(monkeypatch):
    from stock_platform_research import day_quote_cli as dq

    monkeypatch.setattr(dq, "_fetch_ohlc_chunk", lambda s, a, b: (_ for _ in ()).throw(ConnectionError("x")))
    monkeypatch.setattr(
        dq, "_snapshot_fill", lambda symbols, asof: (_ for _ in ()).throw(RuntimeError("snap boom"))
    )
    monkeypatch.setattr("time.sleep", lambda *_: None)

    rows, err = dq._fetch_ohlc(["600000"], "2026-10-30")
    assert rows == {}
    assert err and "snap boom" in err


def test_snapshot_rows_land_in_cache_so_rerun_is_zero_network(tmp_path: Path, monkeypatch):
    """快照补齐的当日行同样入缓存：盘中复跑不再打网络。"""
    from stock_platform_research import day_quote_cli as dq

    monkeypatch.setattr(
        dq,
        "_fetch_ohlc_chunk",
        lambda s, a, b: (_ for _ in ()).throw(ConnectionError("dead")),
    )
    monkeypatch.setattr(
        dq,
        "_snapshot_fill",
        lambda symbols, asof: (
            {s: {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5} for s in symbols},
            None,
        ),
    )
    monkeypatch.setattr("time.sleep", lambda *_: None)

    rows, _ = load_ohlc(["600000"], "2026-10-30", cache_dir=tmp_path, allow_network=True)
    assert rows["600000"]["open"] == 1.0
    blob = json.loads((tmp_path / "ohlc-2026-10-30.json").read_text(encoding="utf-8"))
    assert blob["rows"]["600000"] == {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}


def test_engine_fallback_only_when_quote_date_is_later_than_asof(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(quotes, "load_engine_closes", lambda symbols, day: {"600000": 9.9})

    def _fail(symbols, asof):
        return {}, "down"

    rows, err = load_ohlc(
        ["600000"],
        "2026-10-29",
        cache_dir=tmp_path,
        allow_network=True,
        fetch=_fail,
        selection_asof="2026-10-28",
    )
    assert rows["600000"]["close"] == 9.9
    assert "引擎库收盘兜底" in (err or "")

    # quote_date == asof 时绝不用引擎收盘冒充当日收盘
    same_day, same_err = load_ohlc(
        ["600000"],
        "2026-10-29",
        cache_dir=tmp_path,
        allow_network=True,
        fetch=_fail,
        selection_asof="2026-10-29",
    )
    assert same_day == {}
    assert same_err


def test_engine_fallback_is_not_written_into_ohlc_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(quotes, "load_engine_closes", lambda symbols, day: {"600000": 9.9})

    load_ohlc(
        ["600000"],
        "2026-10-29",
        cache_dir=tmp_path,
        allow_network=True,
        fetch=lambda symbols, day: ({}, "down"),
        selection_asof="2026-10-28",
    )
    assert not (tmp_path / "ohlc-2026-10-29.json").exists()


def test_quotes_module_has_no_top_level_providers_import():
    text = Path(quotes.__file__).read_text(encoding="utf-8")
    hits = [line for line in text.splitlines() if "stock_platform_providers" in line]
    assert hits
    assert all(line[:1].isspace() for line in hits)
