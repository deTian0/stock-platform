"""Daily refresh→brief pipeline tests (injected providers; no public net)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from stock_platform_research.daily_cli import main as daily_main
from stock_platform_research.daily_pipeline import _effective_datasets, run_daily_pipeline
from stock_platform_research.hit_tracking import reset_hit_repository_cache
from stock_platform_research.persistence import reset_brief_repository_cache


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
    # This drives the whole CLI, so it must never inherit ambient config: pin the
    # brief archive to tmp too. Without this the run upserted a fixture brief into
    # the production ./data/stock_platform.db and blanked the daily digest (ADR 0069).
    monkeypatch.setenv(
        "STOCK_PLATFORM_DB_URL", f"sqlite:///{(tmp_path / 'briefs.db').as_posix()}"
    )
    reset_brief_repository_cache()
    reset_hit_repository_cache()
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


def test_daily_pipeline_records_hit_cycle(tmp_path: Path) -> None:
    """X3: pipeline records the recommendation head into the hit cycle; idempotent."""
    asof = date(2026, 9, 2)
    provider = _PipelineProvider(
        {
            "600519": _synth_bars("600519", asof, base=100.0),
            "000001": _synth_bars("000001", asof, base=10.0),
        }
    )
    db = str(tmp_path / "pipeline.db")
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        top_n=2,
        db_url=db,
    )
    assert report.ok
    assert report.hits is not None
    assert report.hits["sessionType"] == "pre_market"
    assert report.hits["pickDate"] == "2026-09-02"
    assert report.hits["recorded"] >= 1

    # Same asof → same-day dedup: nothing new recorded.
    report2 = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        top_n=2,
        db_url=db,
    )
    assert report2.ok
    assert report2.hits is not None
    assert report2.hits["recorded"] == 0

    # Opt-out leaves no hit rows behind.
    report3 = run_daily_pipeline(
        asof=date(2026, 9, 3),
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519"],
        datasets=["daily"],
        top_n=1,
        track_hits=False,
        db_url=db,
    )
    assert report3.ok
    assert report3.hits is None


# ---------- X4: picks ledger + picks ↔ backtest replay ----------


def _bars_frame(by_sym: dict[str, list[dict[str, Any]]]) -> Any:
    """Synth rows (``symbol`` / ``close``) → the backtest bars shape."""
    import pandas as pd

    rows: list[dict[str, Any]] = []
    for code, series in by_sym.items():
        prev = None
        for row in series:
            close = float(row["close"])
            pct = 0.0 if prev in (None, 0) else (close / prev - 1.0)
            rows.append(
                {"code": code, "date": str(row["date"])[:10], "close": close, "pct_chg": pct}
            )
            prev = close
    return pd.DataFrame(rows)


def _pipeline_kwargs(tmp_path: Path, asof: date) -> dict[str, Any]:
    provider = _PipelineProvider(
        {
            "600519": _synth_bars("600519", asof, base=100.0),
            "000001": _synth_bars("000001", asof, base=10.0),
        }
    )
    return dict(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "000001"],
        datasets=["daily"],
        top_n=2,
        db_url=str(tmp_path / "pipeline.db"),
    )


def test_daily_pipeline_appends_picks_ledger_idempotently(tmp_path: Path) -> None:
    """X4: every session's ②A head lands in the append-only ledger, once."""
    asof = date(2026, 9, 2)
    report = run_daily_pipeline(**_pipeline_kwargs(tmp_path, asof))
    assert report.ok
    assert report.picksLedger is not None
    assert report.picksLedger["appended"] >= 1
    ledger = tmp_path / "picks_ledger.jsonl"
    assert ledger.is_file()
    assert Path(report.picksLedger["path"]) == ledger
    first_total = report.picksLedger["total"]

    again = run_daily_pipeline(**_pipeline_kwargs(tmp_path, asof))
    assert again.ok
    assert again.picksLedger is not None
    assert again.picksLedger["appended"] == 0  # same asof regenerated -> no double count
    assert again.picksLedger["total"] == first_total

    nxt = run_daily_pipeline(**_pipeline_kwargs(tmp_path, date(2026, 9, 3)))
    assert nxt.ok
    assert nxt.picksLedger is not None
    assert nxt.picksLedger["appended"] >= 1  # a new session does add rows
    assert nxt.picksLedger["total"] > first_total


def test_daily_pipeline_replays_picks_through_the_shared_engine(tmp_path: Path) -> None:
    """X4: with bars supplied, the ledger is replayed and the JSON is written."""
    asof = date(2026, 9, 2)
    bars = _bars_frame(
        {
            "600519": _synth_bars("600519", date(2026, 10, 9), n=120, base=100.0),
            "000001": _synth_bars("000001", date(2026, 10, 9), n=120, base=10.0),
        }
    )
    report = run_daily_pipeline(
        **_pipeline_kwargs(tmp_path, asof),
        replay_picks=True,
        replay_bars=bars,
        replay_kwargs={"min_hold": 3, "max_positions": 3, "take_profit": 3.0},
    )
    assert report.ok
    assert report.picksReplay is not None
    assert report.picksReplay["entrySource"] == "picks"
    assert report.picksReplay["ok"] is True, report.picksReplay.get("reason")
    # the pick formed a position — it may still be open at the window's end
    assert report.picksReplay["enteredCodes"]
    assert report.picksReplayPath is not None
    payload = json.loads(Path(report.picksReplayPath).read_text(encoding="utf-8"))
    assert payload["entrySource"] == "picks"
    assert payload["equity_curve"], "the full payload keeps the curve"
    # the manifest summary is trimmed — no curve / trade log in it
    assert "equity_curve" not in report.picksReplay
    assert "trades" not in report.picksReplay


def test_daily_pipeline_replay_against_screener_returns_the_delta(tmp_path: Path) -> None:
    asof = date(2026, 9, 2)
    bars = _bars_frame(
        {
            "600519": _synth_bars("600519", date(2026, 10, 9), n=120, base=100.0),
            "000001": _synth_bars("000001", date(2026, 10, 9), n=120, base=10.0),
        }
    )
    report = run_daily_pipeline(
        **_pipeline_kwargs(tmp_path, asof),
        replay_picks=True,
        replay_bars=bars,
        replay_against_screener=True,
        replay_kwargs={
            "picks_kwargs": {"min_hold": 3, "max_positions": 3, "take_profit": 3.0},
            "screener_kwargs": {
                "min_pick_score": 0.0,
                "min_hold": 3,
                "max_positions": 3,
                "max_picks_per_day": 2,
            },
        },
    )
    assert report.ok
    assert report.picksReplay is not None
    assert report.picksReplay["mode"] == "compare"
    assert report.picksReplay["sameDefinition"]["singleLoopDefinition"] is True
    assert "delta" in report.picksReplay
    assert "total_return" in report.picksReplay["delta"]


def test_daily_pipeline_replay_failure_never_breaks_the_brief(tmp_path: Path) -> None:
    """Best-effort: a broken replay lands on the report, the brief still ships."""
    asof = date(2026, 9, 2)
    import pandas as pd

    report = run_daily_pipeline(
        **_pipeline_kwargs(tmp_path, asof),
        replay_picks=True,
        replay_bars=pd.DataFrame({"nope": [1]}),  # missing code/date/close
    )
    assert report.ok, "the brief must survive a replay failure"
    assert report.picksReplay is not None
    assert report.picksReplay["ok"] is False
    assert "error" in report.picksReplay


def test_daily_pipeline_can_opt_out_of_the_ledger(tmp_path: Path) -> None:
    report = run_daily_pipeline(
        **_pipeline_kwargs(tmp_path, date(2026, 9, 2)),
        track_picks_ledger=False,
    )
    assert report.ok
    assert report.picksLedger is None
    assert not (tmp_path / "picks_ledger.jsonl").is_file()


# --- P0-1: dataset narrowing + persist control ------------------------------


class _DailyOnlyProvider(_PipelineProvider):
    """Provider that advertises only `daily` (like the offline bulk source)."""

    capabilities = frozenset({"daily"})


def test_effective_datasets_narrows_to_provider_capabilities() -> None:
    provider = _DailyOnlyProvider({})
    assert _effective_datasets(provider, None) == ["daily"]
    assert _effective_datasets(provider, ["daily", "adj_factor"]) == ["daily"]


def test_effective_datasets_unchanged_for_capability_free_provider() -> None:
    provider = _PipelineProvider({})  # no ``capabilities`` attribute
    assert _effective_datasets(provider, None) is None
    assert _effective_datasets(provider, ["daily", "fund_flow"]) == ["daily", "fund_flow"]


def test_effective_datasets_returns_none_when_nothing_supported() -> None:
    class _NoCaps:
        capabilities = frozenset({"something_else"})

    assert _effective_datasets(_NoCaps(), ["daily"]) is None


# --- live-path regression: providers without ``capabilities`` ----------------
#
# Live HTTP providers (``tushare_http`` / ``cn_tushare_http``) implement only
# ``get_daily`` and declare neither ``capabilities`` nor ``supports``. Before
# this fix the pipeline requested all four datasets, failed three of them for
# every symbol, and failed the whole run at ``stage="refresh"`` — on the very
# path this machine runs in production. Live verification had only exercised
# ``market_db``, so the regression shipped unnoticed.


class _NamedNoCaps:
    """Mimics a live HTTP provider: a name, no capability declaration."""

    def __init__(self, name: str) -> None:
        self.name = name

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        return []


def test_live_provider_capabilities_come_from_the_registry() -> None:
    """``tushare_http`` declares only ``daily`` — honoured without a 2nd list."""
    provider = _NamedNoCaps("tushare_http")
    assert _effective_datasets(provider, None) == ["daily"]
    assert _effective_datasets(provider, ["daily", "fund_flow"]) == ["daily"]


def test_replay_provider_declares_the_full_dataset_set() -> None:
    provider = _NamedNoCaps("replay")
    resolved = _effective_datasets(provider, None)
    assert resolved is not None
    assert {"daily", "adj_factor", "fund_flow", "full_minute"} <= set(resolved)


def test_unknown_provider_name_keeps_requested_datasets() -> None:
    """An unregistered name is 'no information' — never a silent narrowing."""
    provider = _NamedNoCaps("totally_unregistered_provider")
    assert _effective_datasets(provider, None) is None
    assert _effective_datasets(provider, ["daily", "fund_flow"]) == ["daily", "fund_flow"]


def test_nameless_provider_keeps_requested_datasets() -> None:
    class _NoName:
        pass

    assert _effective_datasets(_NoName(), None) is None


def test_live_provider_pipeline_no_longer_fails_on_extra_datasets(
    tmp_path: Path,
) -> None:
    """End-to-end guard: a daily-only live provider must reach the brief."""

    class _LiveLike(_PipelineProvider):
        name = "tushare_http"  # registry says ``daily`` only

    asof = date(2026, 9, 2)
    provider = _LiveLike({"600519": _synth_bars("600519", asof, base=100.0)})
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519"],
        top_n=1,
        db_url=str(tmp_path / "p.db"),
        track_hits=False,
        track_picks_ledger=False,
        persist_db=False,
    )
    assert report.ok, report.error
    assert report.stage == "brief"
    assert report.refresh is not None
    assert report.refresh["datasets"] == ["daily"]  # not all four


def test_pipeline_skips_unsupported_datasets_instead_of_failing(tmp_path: Path) -> None:
    """A `daily`-only provider must still produce a brief (P0-1 regression guard)."""
    asof = date(2026, 9, 2)
    provider = _DailyOnlyProvider(
        {"600519": _synth_bars("600519", asof, base=100.0)}
    )
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519"],
        top_n=1,
        db_url=str(tmp_path / "p.db"),
        track_hits=False,
        track_picks_ledger=False,
        persist_db=False,
    )
    assert report.ok, report.error
    assert report.stage == "brief"
    # Only the supported dataset was attempted.
    assert report.refresh is not None
    assert report.refresh["datasets"] == ["daily"]


def test_pipeline_persist_false_skips_refresh_json(tmp_path: Path) -> None:
    asof = date(2026, 9, 2)
    provider = _PipelineProvider({"600519": _synth_bars("600519", asof, base=100.0)})
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519"],
        datasets=["daily"],
        top_n=1,
        db_url=str(tmp_path / "p.db"),
        track_hits=False,
        track_picks_ledger=False,
        persist_db=False,
        refresh_persist=False,
    )
    assert report.ok
    assert not (tmp_path / "2026-09-02" / "daily_600519.json").is_file()
    # The manifest still records the successful item.
    assert report.refresh is not None
    assert report.refresh["okCount"] == 1


# --- P0-4: gap tolerance on the live path ------------------------------------
#
# A thin symbol (an ETF whose bars stop before ``asof``) produces an empty
# daily frame. That is a *gap*, not a transport error, and it must not abort
# the whole daily run — the panel already tolerates an empty symbol.


class _GapProvider(_PipelineProvider):
    """Serves real bars for one symbol and nothing for another.

    Mirrors the offline bulk provider: rows are returned as a flat list of
    dicts (the pipeline builds a per-symbol frame from them). A symbol in
    ``empty`` contributes no rows, which is exactly what a thin ETF looks
    like downstream — an empty daily frame for that symbol.
    """

    capabilities = frozenset({"daily"})

    def __init__(self, by_sym: dict[str, list[dict[str, Any]]], empty: set[str]) -> None:
        super().__init__(by_sym)
        self._empty = empty

    def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
        if self._empty:
            symbols = [s for s in symbols if s not in self._empty]
        return super().get_daily(symbols, start=start, end=end, asset_type=asset_type)


def _gap_symbols(asof: date) -> dict[str, list[dict[str, Any]]]:
    return {"600519": _synth_bars("600519", asof, base=100.0)}


def test_pipeline_survives_a_thin_symbol_by_default(tmp_path: Path) -> None:
    asof = date(2026, 9, 2)
    provider = _GapProvider(_gap_symbols(asof), empty={"510300"})
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "510300"],
        top_n=1,
        db_url=str(tmp_path / "p.db"),
        track_hits=False,
        track_picks_ledger=False,
        persist_db=False,
    )
    assert report.ok, report.error
    assert report.stage == "brief"
    assert report.refresh is not None
    assert report.refresh["gapCount"] == 1
    assert report.refresh["failCount"] == 0
    assert report.refresh["tolerateGaps"] is True
    assert report.refresh["gaps"][0]["symbol"] == "510300"
    # A tolerated gap is not a failure, so nothing lands in ``failures``.
    assert report.refresh["failures"] == []


def test_pipeline_strict_gaps_fails_the_run(tmp_path: Path) -> None:
    """``refresh_tolerate_gaps=False`` restores the old all-or-nothing gate."""
    asof = date(2026, 9, 2)
    provider = _GapProvider(_gap_symbols(asof), empty={"510300"})
    report = run_daily_pipeline(
        asof=asof,
        provider=provider,
        out_dir=tmp_path,
        symbols=["600519", "510300"],
        top_n=1,
        db_url=str(tmp_path / "p.db"),
        track_hits=False,
        track_picks_ledger=False,
        persist_db=False,
        refresh_tolerate_gaps=False,
    )
    assert not report.ok
    assert report.stage == "refresh"
    assert report.refresh is not None
    assert report.refresh["failCount"] == 1
    assert report.refresh["tolerateGaps"] is False


# --- P0-4: CLI flags ---------------------------------------------------------


def test_daily_cli_gap_tolerance_defaults_on() -> None:
    from stock_platform_research.daily_cli import _resolve_tolerate_gaps

    class _A:
        refresh_tolerate_gaps = None

    assert _resolve_tolerate_gaps(_A()) is True


def test_daily_cli_env_can_pin_strict_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from stock_platform_research.daily_cli import _resolve_tolerate_gaps

    class _A:
        refresh_tolerate_gaps = None

    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_TOLERATE_GAPS", "0")
    assert _resolve_tolerate_gaps(_A()) is False
    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_TOLERATE_GAPS", "false")
    assert _resolve_tolerate_gaps(_A()) is False


def test_daily_cli_explicit_flag_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from stock_platform_research.daily_cli import _resolve_tolerate_gaps

    class _Strict:
        refresh_tolerate_gaps = False

    class _Loose:
        refresh_tolerate_gaps = True

    monkeypatch.setenv("STOCK_PLATFORM_REFRESH_TOLERATE_GAPS", "0")
    assert _resolve_tolerate_gaps(_Loose()) is True  # explicit --refresh-tolerate-gaps
    monkeypatch.delenv("STOCK_PLATFORM_REFRESH_TOLERATE_GAPS", raising=False)
    assert _resolve_tolerate_gaps(_Strict()) is False  # explicit --no-refresh-tolerate-gaps


def test_refresh_cli_exposes_gap_flags() -> None:
    """Both directions exist and default to ``None`` (env-resolved)."""
    import inspect

    from stock_platform_research import refresh_cli

    src = inspect.getsource(refresh_cli.main)
    assert "--tolerate-gaps" in src
    assert "--no-tolerate-gaps" in src
    assert "tolerate_gaps" in src


# --- workbuddy provider wiring (v4.1.8) -------------------------------------
#
# The `workbuddy` preset alone was not enough: `Invoke-DailyPipeline.ps1`
# defaults `--provider` to `replay` and passes it explicitly, which overrides
# any preset. The CLI therefore has to accept `--provider workbuddy` directly,
# and the bridge has to have populated the cache first.


def test_daily_cli_accepts_workbuddy_provider(tmp_path, monkeypatch) -> None:
    """`--provider workbuddy` builds the cache-backed provider."""
    import stock_platform_providers.workbuddy as wb
    from stock_platform_research import daily_cli

    cache = tmp_path / "wb_cache"
    cache.mkdir()
    (cache / "daily_600519.json").write_text(
        json.dumps(
            {
                "symbol": "600519",
                "bars": [
                    {
                        "date": "2026-09-02",
                        "open": 1.0,
                        "high": 1.1,
                        "low": 0.9,
                        "close": 1.05,
                        "volume": 100,
                        "amount": 105.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(wb.ENV_WORKBUDDY_CACHE_DIR, str(cache))

    class _Args:
        provider = "workbuddy"
        fixtures = str(tmp_path)

    provider = daily_cli._build_provider(_Args())
    assert provider.name == "workbuddy"
    assert provider.cache_dir == cache.resolve()


def test_daily_cli_workbuddy_requires_cache_dir(tmp_path, monkeypatch) -> None:
    import stock_platform_providers.workbuddy as wb
    from stock_platform_research import daily_cli

    monkeypatch.delenv(wb.ENV_WORKBUDDY_CACHE_DIR, raising=False)

    class _Args:
        provider = "workbuddy"
        fixtures = str(tmp_path)

    with pytest.raises(SystemExit) as exc:
        daily_cli._build_provider(_Args())
    assert wb.ENV_WORKBUDDY_CACHE_DIR in str(exc.value)


def test_daily_cli_workbuddy_missing_cache_fails_with_actionable_message(
    tmp_path, monkeypatch
) -> None:
    import stock_platform_providers.workbuddy as wb
    from stock_platform_research import daily_cli

    monkeypatch.setenv(wb.ENV_WORKBUDDY_CACHE_DIR, str(tmp_path / "does_not_exist"))

    class _Args:
        provider = "workbuddy"
        fixtures = str(tmp_path)

    with pytest.raises(SystemExit) as exc:
        daily_cli._build_provider(_Args())
    assert "workbuddy-bridge" in str(exc.value)


def test_daily_cli_workbuddy_alias_accepted(tmp_path, monkeypatch) -> None:
    import stock_platform_providers.workbuddy as wb
    from stock_platform_research import daily_cli

    cache = tmp_path / "wb_cache"
    cache.mkdir()
    monkeypatch.setenv(wb.ENV_WORKBUDDY_CACHE_DIR, str(cache))

    class _Args:
        provider = "workbuddy_mcp"
        fixtures = str(tmp_path)

    assert daily_cli._build_provider(_Args()).name == "workbuddy"
