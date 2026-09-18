"""Daily refresh→brief pipeline tests (injected providers; no public net)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from stock_platform_research.daily_cli import main as daily_main
from stock_platform_research.daily_pipeline import run_daily_pipeline


def _synth_bars(symbol: str, asof: date, n: int = 70, base: float = 10.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    d = asof
    closes: list[tuple[date, float]] = []
    while len(closes) < n:
        if d.weekday() < 5:
            idx = n - len(closes)
            px = base + 0.02 * idx + (0.15 if idx % 7 == 0 else 0.0)
            closes.append((d, px))
        d -= timedelta(days=1)
    closes.reverse()
    for day, px in closes:
        rows.append(
            {
                "symbol": symbol,
                "date": day.isoformat(),
                "open": px * 0.99,
                "high": px * 1.01,
                "low": px * 0.98,
                "close": px,
                "volume": 1_000_000,
                "amount": px * 1_000_000,
            }
        )
    return rows


class _PipelineProvider:
    def __init__(self, by_sym: dict[str, list[dict[str, Any]]]) -> None:
        self.by_sym = by_sym

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        out = []
        for sym in symbols:
            for row in self.by_sym.get(sym, []):
                day = date.fromisoformat(str(row["date"])[:10])
                if start and day < start:
                    continue
                if end and day > end:
                    continue
                out.append(row)
        return out

    def get_adj_factor(self, symbols, *, start=None, end=None, kind="qfq"):
        end_d = end or date(2026, 9, 2)
        return [{"symbol": s, "date": end_d.isoformat(), "factor": 1.0, "kind": kind} for s in symbols]

    def get_fund_flow(self, symbols, *, start=None, end=None, limit=120):
        end_d = end or date(2026, 9, 2)
        return [{"symbol": s, "date": end_d.isoformat(), "main_net": 1.0} for s in symbols]

    def get_full_minute(self, symbols, *, trade_date=None, count=300):
        return [
            {
                "symbol": symbols[0],
                "datetime": "2026-09-02 09:31:00",
                "open": 10,
                "close": 10.1,
                "freq": "1m",
            }
        ]


def test_daily_pipeline_refresh_then_brief(tmp_path: Path) -> None:
    asof = date(2026, 9, 2)
    provider = _PipelineProvider(
        {
            "600519": _synth_bars("600519", asof, base=100.0),
            "000001": _synth_bars("000001", asof, base=10.0),
        }
    )
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        top_n=2,
        db_url=str(tmp_path / "pipeline.db"),
    )
    assert report.ok
    assert report.brief_path
    brief = json.loads(Path(report.brief_path).read_text(encoding="utf-8"))
    assert brief["asof"] == "2026-09-02"
    assert brief["environment"] == "SIMULATE"
    assert (tmp_path / "briefs" / "latest.json").is_file()
    assert (tmp_path / "2026-09-02" / "daily_600519.json").is_file()
    from stock_platform_research import SqliteBriefRepository

    stored = SqliteBriefRepository(tmp_path / "pipeline.db").get_by_asof("2026-09-02")
    assert stored is not None
    assert stored.environment == "SIMULATE"

    # Idempotent overwrite
    report2 = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        top_n=1,
        db_url=str(tmp_path / "pipeline.db"),
    )
    assert report2.ok
    brief2 = json.loads(Path(report2.brief_path).read_text(encoding="utf-8"))
    assert brief2["topN"] == 1


def test_daily_pipeline_fail_closed(tmp_path: Path) -> None:
    class _Boom:
        def get_daily(self, *a, **k):
            raise RuntimeError("no data")

        def get_adj_factor(self, *a, **k):
            return []

        def get_fund_flow(self, *a, **k):
            return []

        def get_full_minute(self, *a, **k):
            return []

    report = run_daily_pipeline(
        asof="2026-09-02",
        provider=_Boom(),
        out_dir=tmp_path,
        symbols=["600519"],
        datasets=["daily"],
        max_attempts=1,
        persist_db=False,
    )
    assert not report.ok
    assert (tmp_path / "briefs" / "2026-09-02" / "failure.json").is_file()
    latest = json.loads((tmp_path / "briefs" / "latest.json").read_text(encoding="utf-8"))
    assert latest["ok"] is False


def test_daily_cli_requires_fixtures() -> None:
    try:
        code = daily_main(["--asof", "2026-09-02", "--provider", "replay"])
    except SystemExit as exc:
        code = int(exc.code or 1)
    assert code != 0


def test_daily_cli_tushare_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_PLATFORM_TUSHARE_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        daily_main(["--asof", "2026-09-02", "--provider", "tushare", "--skip-refresh"])
    msg = str(exc.value)
    assert "STOCK_PLATFORM_TUSHARE_TOKEN" in msg


def test_daily_pipeline_repo_fixtures_nonempty_picks(tmp_path: Path) -> None:
    """Documented replay path: sample universe + provider fixtures → exit-ok + picks."""
    from stock_platform_providers import ReplayProvider, ReplayTransport
    from stock_platform_research.universe import default_universe_fixture_path

    repo = Path(__file__).resolve().parents[3]
    fixtures = repo / "packages" / "providers" / "tests" / "fixtures"
    assert fixtures.is_dir()
    provider = ReplayProvider(ReplayTransport(fixtures))
    report = run_daily_pipeline(
        asof=date(2026, 9, 2),
        provider=provider,
        out_dir=tmp_path,
        universe_path=default_universe_fixture_path(),
        top_n=10,
        db_url=str(tmp_path / "pipeline.db"),
    )
    assert report.ok, report.error or report.failures
    assert report.brief_path
    brief = json.loads(Path(report.brief_path).read_text(encoding="utf-8"))
    assert brief["environment"] == "SIMULATE"
    assert len(brief.get("picks") or []) >= 1
    assert (tmp_path / "briefs" / "latest.json").is_file()


def test_daily_cli_settle_after_logs_performance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--settle-after logs brief into JSONL (replay fixtures; settle may stay pending)."""
    from stock_platform_research import daily_cli as daily_cli_mod

    repo = Path(__file__).resolve().parents[3]
    fixtures = repo / "packages" / "providers" / "tests" / "fixtures"
    log_path = tmp_path / "perf.jsonl"
    monkeypatch.setenv("STOCK_PLATFORM_PERFORMANCE_LOG", str(log_path))
    # Avoid engine settle path requiring real market.db in CI
    monkeypatch.setattr(
        "stock_platform_research.performance_cli._build_settle_get_daily",
        lambda: (_ for _ in ()).throw(SystemExit("no engine in test")),
    )
    code = daily_cli_mod.main(
        [
            "--asof",
            "2026-09-02",
            "--provider",
            "replay",
            "--fixtures",
            str(fixtures),
            "--out",
            str(tmp_path / "out"),
            "--skip-refresh",
            "--settle-after",
        ]
    )
    assert code == 0
    assert log_path.is_file()
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
