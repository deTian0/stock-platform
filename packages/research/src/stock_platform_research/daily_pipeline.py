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
from typing import Any

import pandas as pd

from .brief import build_premarket_brief, write_brief_csv
from .panel import build_cross_section_panel, panel_to_csv
from .refresh import RefreshReport, default_refresh_dir, run_refresh
from .universe import default_universe_fixture_path, load_universe


@dataclass
class DailyPipelineReport:
    asof: str
    ok: bool
    stage: str
    out_dir: str
    refresh: dict[str, Any] | None = None
    brief: dict[str, Any] | None = None
    brief_path: str | None = None
    panel_path: str | None = None
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
    symbols: list[str] | None = None,
    datasets: list[str] | None = None,
    top_n: int = 10,
    lookback_days: int = 120,
    skip_refresh: bool = False,
    max_attempts: int = 3,
) -> DailyPipelineReport:
    """Run refresh (optional) then build+persist premarket brief.

    Idempotent for the same ``asof``: overwrites brief/panel/manifest under briefs/.
    On failure writes ``failure.json`` and returns ``ok=False`` (fail-closed).
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
    try:
        resolved = symbols
        if resolved is None:
            resolved = load_universe(univ, tier=universe_tier)

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
        )
        brief_json = day_dir / "brief.json"
        brief_csv = day_dir / "brief.csv"
        brief_json.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_brief_csv(brief, brief_csv)

        ok_report = DailyPipelineReport(
            asof=asof_s,
            ok=True,
            stage="brief",
            out_dir=str(root),
            refresh=refresh_payload,
            brief={
                "asof": brief["asof"],
                "universeSize": brief["universeSize"],
                "panelSize": brief["panelSize"],
                "topN": brief["topN"],
                "pickCount": len(brief.get("picks") or []),
            },
            brief_path=str(brief_json),
            panel_path=str(panel_path),
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
            error=f"{type(exc).__name__}: {exc}",
            failures=[{"error": str(exc), "trace": traceback.format_exc()[-2000:]}],
        )
        _write_failure(day_dir, briefs_root, fail)
        return fail


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
