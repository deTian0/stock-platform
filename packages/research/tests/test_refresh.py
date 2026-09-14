"""CN daily / full_minute refresh job tests (injected providers; no public net)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_research.refresh import run_refresh
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
