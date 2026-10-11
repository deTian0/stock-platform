"""Daily pipeline debate lane — injection + 误判不进绩效 invariant (S5).

The research package stays agents-free: the lane is injected as a ``debate_runner``.
The invariant these tests pin: with the lane on, the brief JSON, the picks ledger
and the hit cycle are **identical** to a lane-off run — a wrong debate verdict can
never reach the recommendation accounting.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from stock_platform_research.daily_pipeline import run_daily_pipeline

ASOF = date(2026, 9, 2)


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
        end_d = end or ASOF
        return [{"symbol": s, "date": end_d.isoformat(), "factor": 1.0, "kind": kind} for s in symbols]

    def get_fund_flow(self, symbols, *, start=None, end=None, limit=120):
        return [{"symbol": s, "date": ASOF.isoformat(), "main_net": 1.0} for s in symbols]


def _provider() -> _PipelineProvider:
    return _PipelineProvider(
        {
            "600519": _synth_bars("600519", ASOF, base=100.0),
            "000001": _synth_bars("000001", ASOF, base=10.0),
        }
    )


def _bogus_runner(**kwargs: Any) -> dict[str, Any]:
    """A lane carrying a deliberately WRONG verdict — it must never leak."""
    brief = kwargs.get("brief") or {}
    return {
        "enabled": True,
        "engine": "deterministic",
        "requestedEngine": "deterministic",
        "asof": brief.get("asof"),
        "picksConsidered": len(brief.get("picks") or []),
        "debates": [
            {
                "rank": p.get("rank"),
                "symbol": p.get("symbol"),
                "debate": {"verdict": "Sell", "kind": "debate"},
            }
            for p in (brief.get("picks") or [])
        ],
        "warnings": [],
        "degraded": False,
        "advisory": True,
        "excludedFromPerformance": True,
        "budget": {"maxCalls": 6, "maxTokensSoft": None, "callsUsed": 0, "tokensEst": 0},
    }


def _run(out: Path, *, runner=None, engine=None) -> Any:
    return run_daily_pipeline(
        asof=ASOF,
        provider=_provider(),
        out_dir=out,
        symbols=["600519", "000001"],
        datasets=["daily"],
        top_n=2,
        db_url=str(out / "pipeline.db"),
        debate_runner=runner,
        debate_engine=engine,
    )


def test_no_runner_leaves_debates_none(tmp_path: Path) -> None:
    report = _run(tmp_path / "a")
    assert report.ok
    assert report.debates is None
    assert not (tmp_path / "a" / "briefs" / "2026-09-02" / "debates.json").is_file()


def test_engine_off_never_calls_the_runner(tmp_path: Path) -> None:
    calls = {"n": 0}

    def _spy(**kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        return {"enabled": False, "engine": "off", "debates": [], "debateCount": 0}

    report = _run(tmp_path / "a", runner=_spy, engine="off")
    assert report.ok
    assert calls["n"] == 0
    assert report.debates is None


def test_runner_writes_debates_json_and_manifest(tmp_path: Path) -> None:
    report = _run(tmp_path / "a", runner=_bogus_runner, engine="deterministic")
    assert report.ok
    assert report.debates is not None
    assert report.debates["ok"] is True
    day_dir = tmp_path / "a" / "briefs" / "2026-09-02"
    brief = json.loads((day_dir / "brief.json").read_text(encoding="utf-8"))
    n_picks = len(brief["picks"])
    assert n_picks >= 1
    assert report.debates["debateCount"] == n_picks
    assert report.debates["excludedFromPerformance"] is True
    assert len(report.debates["verdicts"]) == n_picks
    assert (day_dir / "debates.json").is_file()
    full = json.loads((day_dir / "debates.json").read_text(encoding="utf-8"))
    assert len(full["debates"]) == n_picks
    manifest = json.loads((day_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["debates"]["debateCount"] == n_picks


def test_lane_leaves_brief_ledger_and_hits_identical(tmp_path: Path) -> None:
    """误判不进绩效: only the debate lane may differ between the two runs."""
    off = _run(tmp_path / "off")
    on = _run(tmp_path / "on", runner=_bogus_runner, engine="deterministic")
    assert off.ok and on.ok

    brief_off = (tmp_path / "off" / "briefs" / "2026-09-02" / "brief.json").read_bytes()
    brief_on = (tmp_path / "on" / "briefs" / "2026-09-02" / "brief.json").read_bytes()
    assert brief_off == brief_on  # bogus Sell verdicts never reach the brief

    ledger_off = (tmp_path / "off" / "picks_ledger.jsonl").read_bytes()
    ledger_on = (tmp_path / "on" / "picks_ledger.jsonl").read_bytes()
    assert ledger_off == ledger_on  # and never reach the picks ledger

    assert off.hits == on.hits  # nor the hit cycle
    assert (tmp_path / "off" / "picks_ledger.jsonl").read_text(encoding="utf-8").strip()
    assert not (tmp_path / "off" / "briefs" / "2026-09-02" / "debates.json").is_file()
    assert (tmp_path / "on" / "briefs" / "2026-09-02" / "debates.json").is_file()


def test_runner_failure_is_best_effort(tmp_path: Path) -> None:
    def _boom(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("lane exploded")

    report = _run(tmp_path / "a", runner=_boom, engine="llm")
    assert report.ok  # the brief is unaffected
    assert report.debates is not None
    assert report.debates["ok"] is False
    assert "lane exploded" in report.debates["error"]
