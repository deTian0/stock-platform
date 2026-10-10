"""Daily pipeline: refresh → brief (idempotent per asof; fail-closed).

Writes under ``{out}/briefs/{asof}/`` plus ``{out}/briefs/latest.json``.
Default provider path is replay (CI zero public net).
"""

from __future__ import annotations

import json
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .brief import build_premarket_brief, write_brief_csv
from .hit_tracking import PRE_MARKET, open_hit_repository, track_brief_hits
from .market_universe import resolve_universe
from .panel import build_cross_section_panel, panel_to_csv
from .performance import append_jsonl  # noqa: F401 (ledger writer lives in picks_backtest)
from .persistence import open_brief_repository
from .picks_backtest import (
    PICK_LEDGER_FILENAME,
    append_picks_ledger,
    compare_picks_vs_screener,
    load_picks_ledger,
    picks_from_brief,
    run_picks_backtest,
)
from .refresh import RefreshReport, default_refresh_dir, run_refresh
from .universe import UNIVERSE_SOURCES, default_universe_fixture_path


@dataclass
class DailyPipelineReport:
    asof: str
    ok: bool
    stage: str
    out_dir: str
    universe: dict[str, Any] | None = None
    refresh: dict[str, Any] | None = None
    brief: dict[str, Any] | None = None
    brief_path: str | None = None
    panel_path: str | None = None
    hits: dict[str, Any] | None = None
    picksLedger: dict[str, Any] | None = None
    picksReplay: dict[str, Any] | None = None
    picksReplayPath: str | None = None
    error: str | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_briefs_dir(refresh_out: str | Path | None = None) -> Path:
    root = Path(refresh_out) if refresh_out else default_refresh_dir()
    return root / "briefs"


def run_daily_pipeline(
    *,
    asof: date | str,
    provider: Any,
    out_dir: str | Path | None = None,
    universe_path: str | Path | None = None,
    universe_tier: str | None = None,
    universe_source: str = "config",
    market_symbol_source: Any | None = None,
    market_universe_kwargs: dict[str, Any] | None = None,
    symbols: list[str] | None = None,
    datasets: list[str] | None = None,
    holdings: list[dict[str, Any]] | None = None,
    top_n: int = 10,
    lookback_days: int = 120,
    skip_refresh: bool = False,
    max_attempts: int = 3,
    persist_db: bool = True,
    track_hits: bool = True,
    hit_boards: list[str] | None = None,
    track_picks_ledger: bool = True,
    picks_ledger_path: str | Path | None = None,
    replay_picks: bool = False,
    replay_bars: pd.DataFrame | None = None,
    replay_against_screener: bool = False,
    replay_kwargs: dict[str, Any] | None = None,
    db_url: str | None = None,
) -> DailyPipelineReport:
    """Run refresh (optional) then build+persist premarket brief.

    Idempotent for the same ``asof``: overwrites brief/panel/manifest under briefs/.
    When ``persist_db`` is True (default), also upserts into the SQLite brief
    repository (``STOCK_PLATFORM_DB_URL`` / ADR 0049) — shared with Workbench.
    On failure writes ``failure.json`` and returns ``ok=False`` (fail-closed).

    ``X2``: pass ``holdings`` (book rows with ``code`` / ``entry_price``) to fill
    the ③A 持仓 and ③B 操作建议 boards; without it those two boards are empty by
    design (fail-closed, never guessed).

    ``X3``: ``track_hits`` (default on) records the ②A recommendation head into the
    hit cycle in the same SQLite (``hit_boards`` overrides the board set). Tracking
    is best-effort — a failure lands on ``report.hits["error"]``, never on the brief.

    ``X4``: every session automatically appends the ②A head into the append-only
    **picks ledger** (``track_picks_ledger``, default on; ``picks_ledger_path``
    overrides ``{out}/picks_ledger.jsonl``), so the recommendations enter the
    backtest-comparison data source without a second call. Pass ``replay_bars``
    **and** ``replay_picks=True`` to also replay the accumulated ledger through the
    *same* engine as the screener (:func:`picks_backtest.run_picks_backtest`) and
    write ``{asof}/picks_replay.json``; ``replay_against_screener`` additionally
    returns the screener side and the metric delta. Both stages are best-effort —
    a failure lands on ``report.picksReplay["error"]`` and never breaks the brief.
    """
    if isinstance(asof, str):
        asof_d = date.fromisoformat(asof[:10])
        asof_s = asof_d.isoformat()
    else:
        asof_d = asof
        asof_s = asof.isoformat()

    root = Path(out_dir) if out_dir else default_refresh_dir()
    briefs_root = root / "briefs"
    day_dir = briefs_root / asof_s
    day_dir.mkdir(parents=True, exist_ok=True)

    univ = universe_path or default_universe_fixture_path()
    universe_meta: dict[str, Any] = {
        "source": str(universe_source or "config").strip().lower(),
        "sources": list(UNIVERSE_SOURCES),
    }
    try:
        if symbols is not None:
            resolved = symbols
            universe_meta["explicitSymbols"] = True
        else:
            # X1: ``market_db`` needs the asof / window of this very run.
            market_kwargs = dict(market_universe_kwargs or {})
            market_kwargs.setdefault("asof", asof_d)
            market_kwargs.setdefault("lookback_days", lookback_days)
            resolved = resolve_universe(
                source=universe_source,
                path=univ,
                tier=universe_tier,
                market_symbol_source=market_symbol_source,
                **market_kwargs,
            )
        universe_meta["size"] = len(resolved)

        refresh_payload: dict[str, Any] | None = None
        if not skip_refresh:
            report: RefreshReport = run_refresh(
                asof=asof_d,
                provider=provider,
                out_dir=root,
                universe_path=None,
                symbols=resolved,
                datasets=datasets,
                lookback_days=lookback_days,
                max_attempts=max_attempts,
            )
            refresh_payload = report.to_dict()
            if not report.ok:
                fail = DailyPipelineReport(
                    asof=asof_s,
                    ok=False,
                    stage="refresh",
                    out_dir=str(root),
                    universe=dict(universe_meta),
                    refresh=refresh_payload,
                    error="refresh failed",
                    failures=refresh_payload.get("failures") or [],
                )
                _write_failure(day_dir, briefs_root, fail)
                return fail

        # Prefer building panel from injected provider (works for replay fixtures
        # and for refresh-then-replay callers who rebind provider).
        panel = build_cross_section_panel(
            asof=asof_d,
            symbols=resolved,
            daily_provider=provider,
            lookback_calendar_days=lookback_days,
            adjust_kind=None,
        )
        panel_path = day_dir / "panel.csv"
        panel_to_csv(panel, panel_path)

        brief = build_premarket_brief(
            asof=asof_d,
            symbols=resolved,
            panel=panel,
            top_n=top_n,
            universe_tier=universe_tier,
            holdings=holdings,
        )
        brief_json = day_dir / "brief.json"
        brief_csv = day_dir / "brief.csv"
        brief_json.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_brief_csv(brief, brief_csv)

        if persist_db:
            # Authority archive (U2); JSON under briefs/ remains optional export.
            open_brief_repository(db_url).save(brief, symbols=resolved)

        # X3: record the pre-market recommendation head into the hit cycle.
        # Tracking must never break the brief — any failure is captured, not raised.
        hits_payload: dict[str, Any] | None = None
        if track_hits:
            try:
                hit_repo = open_hit_repository(db_url)
                tracked = track_brief_hits(
                    hit_repo,
                    brief,
                    boards=tuple(hit_boards) if hit_boards else ("quality",),
                    session_type=PRE_MARKET,
                )
                hits_payload = {
                    "sessionType": tracked["sessionType"],
                    "pickDate": tracked["pickDate"],
                    "boards": tracked["boards"],
                    "recorded": tracked["recorded"],
                    "skipped": tracked["skipped"],
                }
            except Exception as exc:  # noqa: BLE001 — tracking is best-effort
                hits_payload = {"recorded": 0, "error": f"{type(exc).__name__}: {exc}"}

        # X4: every session appends the ②A head into the append-only picks ledger
        # (deduped on (date, code)), so the recommendations enter the
        # backtest-comparison data source with no extra call. Best-effort.
        ledger_file = Path(picks_ledger_path) if picks_ledger_path else (root / PICK_LEDGER_FILENAME)
        ledger_payload: dict[str, Any] | None = None
        if track_picks_ledger:
            try:
                appended = append_picks_ledger(ledger_file, picks_from_brief(brief))
                ledger_payload = {
                    "path": str(ledger_file),
                    "appended": len(appended),
                    "total": len(load_picks_ledger(ledger_file)),
                }
            except Exception as exc:  # noqa: BLE001 — ledger is best-effort
                ledger_payload = {
                    "path": str(ledger_file),
                    "appended": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        # X4: optional replay of the *accumulated* ledger through the same engine
        # the screener backtest runs. Needs caller-supplied bars (the daily brief
        # itself has no forward window). Best-effort, like the hit tracking.
        replay_payload: dict[str, Any] | None = None
        replay_path: str | None = None
        if replay_picks and replay_bars is not None:
            try:
                ledger_rows = load_picks_ledger(ledger_file) if ledger_file.is_file() else []
                if not ledger_rows:
                    ledger_rows = picks_from_brief(brief)
                kw = dict(replay_kwargs or {})
                if replay_against_screener:
                    replay_payload = compare_picks_vs_screener(ledger_rows, replay_bars, **kw)
                else:
                    replay_payload = run_picks_backtest(ledger_rows, replay_bars, **kw)
                replay_payload["asof"] = asof_s
                replay_payload["ledgerPath"] = str(ledger_file)
                replay_file = day_dir / "picks_replay.json"
                replay_file.write_text(
                    json.dumps(replay_payload, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
                replay_path = str(replay_file)
            except Exception as exc:  # noqa: BLE001 — replay is best-effort
                replay_payload = {
                    "ok": False,
                    "ledgerPath": str(ledger_file),
                    "error": f"{type(exc).__name__}: {exc}",
                }

        ok_report = DailyPipelineReport(
            asof=asof_s,
            ok=True,
            stage="brief",
            out_dir=str(root),
            universe=dict(universe_meta),
            refresh=refresh_payload,
            brief={
                "asof": brief["asof"],
                "universeSize": brief["universeSize"],
                "panelSize": brief["panelSize"],
                "topN": brief["topN"],
                "pickCount": len(brief.get("picks") or []),
                "rankingsCounts": brief.get("rankingsCounts") or {},
            },
            brief_path=str(brief_json),
            panel_path=str(panel_path),
            hits=hits_payload,
            picksLedger=ledger_payload,
            picksReplay=_replay_summary(replay_payload) if replay_payload else None,
            picksReplayPath=replay_path,
        )
        latest = {
            "asof": asof_s,
            "ok": True,
            "briefPath": str(brief_json),
            "panelPath": str(panel_path),
            "dayDir": str(day_dir),
            "updatedAt": pd.Timestamp.now("UTC").isoformat(),
        }
        (briefs_root / "latest.json").write_text(
            json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (day_dir / "manifest.json").write_text(
            json.dumps(ok_report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return ok_report
    except Exception as exc:  # noqa: BLE001 — pipeline boundary; fail-closed report
        fail = DailyPipelineReport(
            asof=asof_s,
            ok=False,
            stage="error",
            out_dir=str(root),
            universe=dict(universe_meta),
            error=f"{type(exc).__name__}: {exc}",
            failures=[{"error": str(exc), "trace": traceback.format_exc()[-2000:]}],
        )
        _write_failure(day_dir, briefs_root, fail)
        return fail


def _replay_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Trim a replay / comparison payload for the manifest.

    The full payload (including the equity curve and the trade log) is written to
    ``{asof}/picks_replay.json``; the manifest only needs the metrics, the params
    and the counts, so a long replay cannot balloon ``manifest.json``.
    """
    if "picks" in payload and "screener" in payload:  # compare-shaped payload
        return {
            "mode": "compare",
            "ok": payload.get("ok"),
            "delta": payload.get("delta"),
            "sameDefinition": payload.get("sameDefinition"),
            "picks": _replay_summary(payload.get("picks") or {}),
            "screener": _replay_summary(payload.get("screener") or {}),
        }
    out = {k: v for k, v in payload.items() if k not in {"equity_curve", "trades"}}
    out["tradeCount"] = len(payload.get("trades") or [])
    out["curvePoints"] = len(payload.get("equity_curve") or [])
    return out


def _write_failure(day_dir: Path, briefs_root: Path, report: DailyPipelineReport) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    (day_dir / "failure.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (briefs_root / "latest.json").write_text(
        json.dumps(
            {"asof": report.asof, "ok": False, "error": report.error, "dayDir": str(day_dir)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
