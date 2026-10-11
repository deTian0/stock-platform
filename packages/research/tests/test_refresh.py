"""CN daily / full_minute refresh job tests (injected providers; no public net)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from stock_platform_research.refresh import (
    RateLimiter,
    default_min_interval,
    default_workers,
    run_refresh,
)
from stock_platform_research.refresh_cli import main as refresh_main
from stock_platform_research.universe import UniverseEmptyError


class _Flaky:
    def __init__(self) -> None:
        self.daily_calls = 0

    def get_daily(self, symbols: list[str], *, start=None, end=None, asset_type="stock"):
        self.daily_calls += 1
        if self.daily_calls < 3:
            raise RuntimeError("transient")
        sym = symbols[0]
        return [
            {
                "symbol": sym,
                "date": "2026-09-02",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
            }
        ]

    def get_adj_factor(self, symbols: list[str], *, start=None, end=None, kind="qfq"):
        return [{"symbol": symbols[0], "date": "2026-09-02", "factor": 1.0, "kind": kind}]

    def get_fund_flow(self, symbols: list[str], *, start=None, end=None, limit=120):
        return [{"symbol": symbols[0], "date": "2026-09-02", "main_net": 1.0}]

    def get_full_minute(self, symbols: list[str], *, trade_date=None, count=300):
        return [
            {
                "symbol": symbols[0],
                "datetime": "2026-09-02 09:31:00",
                "open": 10,
                "close": 10.1,
                "freq": "1m",
            }
        ]


def test_refresh_retries_and_persists(tmp_path: Path) -> None:
    sleeps: list[float] = []
    provider = _Flaky()
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519"],
        datasets=["daily", "full_minute"],
        max_attempts=3,
        sleeper=sleeps.append,
    )
    assert report.ok
    assert provider.daily_calls == 3
    assert len(sleeps) == 2
    day_dir = tmp_path / "2026-09-02"
    daily = (day_dir / "daily_600519.json").read_text(encoding="utf-8")
    assert "10.5" in daily
    assert (day_dir / "full_minute_600519.json").is_file()
    latest = (tmp_path / "latest.json").read_text(encoding="utf-8")
    assert '"ok": true' in latest.replace(" ", "").replace("true", " true") or '"ok": true' in latest


def test_refresh_empty_universe_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(UniverseEmptyError):
        run_refresh(
            asof="2026-09-02",
            provider=_Flaky(),
            out_dir=tmp_path,
            symbols=[],
        )


def test_refresh_reports_persistent_failure(tmp_path: Path) -> None:
    class Boom:
        def get_daily(self, symbols, **kwargs):
            raise RuntimeError("hard fail")

    report = run_refresh(
        asof="2026-09-02",
        provider=Boom(),
        out_dir=tmp_path,
        symbols=["000001"],
        datasets=["daily"],
        max_attempts=2,
        sleeper=lambda _s: None,
    )
    assert report.ok is False
    assert report.to_dict()["failCount"] == 1
    assert "hard fail" in (report.items[0].error or "")


def test_refresh_cli_replay_fixtures(tmp_path: Path) -> None:
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    (fixtures / "daily_600519.json").write_text(
        '[{"symbol":"600519","date":"2026-09-02","open":1,"high":1,"low":1,"close":1,"volume":1}]',
        encoding="utf-8",
    )
    universe = tmp_path / "u.json"
    universe.write_text('{"symbols":["600519"]}', encoding="utf-8")
    out = tmp_path / "out"
    code = refresh_main(
        [
            "--asof",
            "2026-09-02",
            "--universe",
            str(universe),
            "--out",
            str(out),
            "--datasets",
            "daily",
            "--provider",
            "replay",
            "--fixtures",
            str(fixtures),
            "--max-attempts",
            "1",
        ]
    )
    assert code == 0
    assert (out / "2026-09-02" / "daily_600519.json").is_file()
    assert (out / "latest.json").is_file()


# --- P0-1: concurrency, rate limiting, bulk --------------------------------


class _SlowCounting:
    """Counts concurrent in-flight calls and records each start time."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.starts: list[float] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()

    def get_daily(self, symbols: list[str], *, start=None, end=None, asset_type="stock"):
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            self.starts.append(time.monotonic())
        try:
            time.sleep(self.delay)
            return [{"symbol": symbols[0], "date": "2026-09-02", "close": 10.0, "volume": 1}]
        finally:
            with self._lock:
                self.in_flight -= 1


def test_serial_default_stays_serial(tmp_path: Path) -> None:
    """No workers → one call at a time (pre-P0-1 behaviour preserved)."""
    provider = _SlowCounting(delay=0.02)
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001", "600036"],
        datasets=["daily"],
        workers=1,
    )
    assert report.ok
    assert provider.max_in_flight == 1


def test_workers_parallelise_the_per_symbol_path(tmp_path: Path) -> None:
    provider = _SlowCounting(delay=0.05)
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001", "600036", "601318"],
        datasets=["daily"],
        workers=4,
        min_interval=0.0,
    )
    assert report.ok
    assert len(report.items) == 4
    assert provider.max_in_flight > 1  # actually overlapped


def test_rate_limiter_paces_aggregate_calls() -> None:
    """workers share one gate: N calls cannot be faster than (N-1)*interval."""
    starts: list[float] = []
    sleeps: list[float] = []

    class _Clock:
        def __init__(self) -> None:
            self.t = 0.0

        def __call__(self) -> float:
            return self.t

        def sleep(self, sec: float) -> None:
            sleeps.append(sec)
            self.t += sec

    clock = _Clock()
    limiter = RateLimiter(1.0, sleeper=clock.sleep, clock=clock)
    for _ in range(3):
        limiter.acquire()
        starts.append(clock.t)

    # Invariant: consecutive acquisitions are spaced by at least the interval.
    # (The first acquisition may also wait, because the gate compares against a
    # virtual clock starting at 0 — the point is spacing, not a free first call.)
    assert starts[1] - starts[0] >= 1.0
    assert starts[2] - starts[1] >= 1.0
    assert sum(sleeps) >= 2.0


def test_rate_limiter_zero_interval_is_noop() -> None:
    sleeps: list[float] = []
    limiter = RateLimiter(0.0, sleeper=sleeps.append)
    limiter.acquire()
    limiter.acquire()
    assert sleeps == []


def test_refresh_workers_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_REFRESH_WORKERS", raising=False)
    assert default_workers() == 1
    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_WORKERS", "8")
    assert default_workers() == 8
    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_WORKERS", "garbage")
    assert default_workers() == 1  # never raises on bad config


def test_refresh_min_interval_env_falls_back_to_em(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_REFRESH_MIN_INTERVAL", raising=False)
    monkeypatch.setenv("EM_MIN_INTERVAL", "1.5")
    assert default_min_interval() == pytest.approx(1.5)
    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_MIN_INTERVAL", "0")
    assert default_min_interval() == 0.0


class _Bulk:
    """Bulk-capable provider: one call serves every symbol."""

    name = "bulk_fake"
    capabilities = frozenset({"daily"})

    def __init__(self) -> None:
        self.bulk_calls = 0
        self.per_symbol_calls = 0

    def bulk_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        self.bulk_calls += 1
        return {
            s: [{"symbol": s, "date": "2026-09-02", "close": 10.0, "volume": 1}]
            for s in symbols
        }

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        self.per_symbol_calls += 1
        return [{"symbol": symbols[0], "date": "2026-09-02", "close": 10.0, "volume": 1}]


def test_bulk_path_uses_one_call(tmp_path: Path) -> None:
    provider = _Bulk()
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001", "600036"],
        datasets=["daily"],
    )
    assert report.ok
    assert provider.bulk_calls == 1  # one pass for the whole universe
    assert provider.per_symbol_calls == 0
    assert len(report.items) == 3
    day = tmp_path / "2026-09-02"
    assert (day / "daily_600519.json").is_file()
    assert (day / "daily_600036.json").is_file()


def test_bulk_path_gap_is_reported_not_fatal(tmp_path: Path) -> None:
    """A symbol with no bars is a *gap* (reported), not a run failure.

    The cross-section panel already drops symbols lacking a bar on ``asof``
    (strict PIT), so one thin symbol must not fail the whole daily run.
    """

    class _PartialBulk(_Bulk):
        def bulk_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
            out = super().bulk_daily(symbols, start=start, end=end, asset_type=asset_type)
            out.pop("000001", None)  # one symbol has no bars
            return out

    report = run_refresh(
        asof="2026-09-02",
        provider=_PartialBulk(),
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
    )
    assert report.ok is True  # a gap does not fail the run
    payload = report.to_dict()
    assert payload["gapCount"] == 1
    assert payload["failCount"] == 0
    assert payload["failures"] == []
    assert [g["symbol"] for g in payload["gaps"]] == ["000001"]
    assert "empty daily bars" in payload["gaps"][0]["error"]


def test_bulk_path_gap_strict_when_tolerance_disabled(tmp_path: Path) -> None:
    """``tolerate_gaps=False`` restores all-or-nothing gating."""

    class _PartialBulk(_Bulk):
        def bulk_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
            out = super().bulk_daily(symbols, start=start, end=end, asset_type=asset_type)
            out.pop("000001", None)
            return out

    report = run_refresh(
        asof="2026-09-02",
        provider=_PartialBulk(),
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        tolerate_gaps=False,
    )
    assert report.ok is False
    payload = report.to_dict()
    assert payload["failCount"] == 1
    assert payload["tolerateGaps"] is False
    assert payload["failures"][0]["symbol"] == "000001"


def test_gap_classification_is_daily_only(tmp_path: Path) -> None:
    """Only a ``daily`` empty-bar item is a tolerable gap.

    An empty result on another dataset is not an error at all (the
    ``empty daily bars`` marker is raised for ``daily`` only), so it can never
    be laundered into a tolerated gap either.
    """
    from stock_platform_research.refresh import (
        EMPTY_BARS_MARKER,
        RefreshItemResult,
    )

    daily_gap = RefreshItemResult(
        symbol="510300",
        dataset="daily",
        ok=False,
        attempts=3,
        error=f"RefreshError: {EMPTY_BARS_MARKER} (fail-closed)",
    )
    minute_gap = RefreshItemResult(
        symbol="510300",
        dataset="full_minute",
        ok=False,
        attempts=3,
        error=f"RefreshError: {EMPTY_BARS_MARKER} (fail-closed)",
    )
    real_error = RefreshItemResult(
        symbol="510300",
        dataset="daily",
        ok=False,
        attempts=3,
        error="RefreshError: connection reset",
    )
    ok_item = RefreshItemResult(
        symbol="600519", dataset="daily", ok=True, attempts=1, rows=80
    )

    assert daily_gap.is_gap is True
    assert minute_gap.is_gap is False  # not a tolerable dataset
    assert real_error.is_gap is False  # transport error, not a data gap
    assert ok_item.is_gap is False


class _MixedPerSymbol:
    """Per-symbol provider: one gap (empty daily) + one hard error."""

    name = "mixed_fake"
    capabilities = frozenset({"daily"})

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        sym = symbols[0]
        if sym == "000001":
            return []  # -> "empty daily bars" gap
        if sym == "600036":
            raise RuntimeError("connection reset")  # hard error
        return [{"symbol": sym, "date": "2026-09-02", "close": 10.0, "volume": 1}]


def test_tolerated_gap_does_not_hide_other_failures(tmp_path: Path) -> None:
    """A real error alongside a gap must still fail the run."""
    report = run_refresh(
        asof="2026-09-02",
        provider=_MixedPerSymbol(),
        out_dir=tmp_path,
        symbols=["600519", "000001", "600036"],
        datasets=["daily"],
        workers=1,
        max_attempts=1,
        sleeper=lambda _s: None,
    )
    assert report.ok is False
    payload = report.to_dict()
    assert payload["gapCount"] == 1
    assert payload["failCount"] == 1
    assert payload["failures"][0]["symbol"] == "600036"
    assert [g["symbol"] for g in payload["gaps"]] == ["000001"]


def test_hard_error_is_never_a_gap(tmp_path: Path) -> None:
    """A transport error must not be laundered into a tolerable gap."""

    class _Boom(_Bulk):
        def bulk_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
            raise RuntimeError("connection reset")

    report = run_refresh(
        asof="2026-09-02",
        provider=_Boom(),
        out_dir=tmp_path,
        symbols=["600519"],
        datasets=["daily"],
        max_attempts=1,
        sleeper=lambda _s: None,
    )
    assert report.ok is False
    payload = report.to_dict()
    assert payload["gapCount"] == 0
    assert payload["failCount"] == 1


def test_bulk_disabled_falls_back_to_per_symbol(tmp_path: Path) -> None:
    provider = _Bulk()
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        bulk=False,
        workers=1,
    )
    assert report.ok
    assert provider.bulk_calls == 0
    assert provider.per_symbol_calls == 2


def test_bulk_not_used_when_dataset_unsupported(tmp_path: Path) -> None:
    """A bulk provider only serving `daily` must not silently drop other datasets."""

    class _DailyOnly(_Bulk):
        def __init__(self) -> None:
            super().__init__()
            self.minute_calls = 0

        def get_full_minute(self, symbols, *, trade_date=None, count=300):
            self.minute_calls += 1
            return [{"symbol": symbols[0], "datetime": "2026-09-02 09:31:00", "close": 10.0}]

    provider = _DailyOnly()
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519"],
        datasets=["daily", "full_minute"],
        workers=1,
    )
    assert report.ok
    assert provider.bulk_calls == 0  # fell back for the whole run
    assert provider.minute_calls == 1
    assert (tmp_path / "2026-09-02" / "full_minute_600519.json").is_file()


def test_workers_result_order_is_stable(tmp_path: Path) -> None:
    """Threading must not shuffle the reported (symbol, dataset) ordering."""
    provider = _SlowCounting(delay=0.01)
    symbols = ["600519", "000001", "600036", "601318", "000002"]
    report = run_refresh(
        asof="2026-09-02",
        provider=provider,
        out_dir=tmp_path,
        symbols=symbols,
        datasets=["daily"],
        workers=4,
        min_interval=0.0,
    )
    assert [i.symbol for i in report.items] == symbols

