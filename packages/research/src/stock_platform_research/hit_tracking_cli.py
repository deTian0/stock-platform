"""CLI ``stock-platform-hits``: record / query the hit cycle (X3).

Examples::

    stock-platform-hits                      # markdown report of all three views
    stock-platform-hits --summary            # JSON snapshot (three cumulatives)
    stock-platform-hits --details --session pre_market --limit 50
    stock-platform-hits --track-brief briefs/2026-09-03/brief.json
    stock-platform-hits --track-json picks.json --session pre_market
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .hit_tracking import (
    HIT_SESSION_TYPES,
    PRE_MARKET,
    format_hit_report,
    hit_tracking_snapshot,
    open_hit_repository,
    track_brief_hits,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Hit tracking: a-stock-engine 10-session cycle on the platform SQLite (X3)"
    )
    p.add_argument(
        "--db",
        default=None,
        help="SQLite path/URL (default STOCK_PLATFORM_DB_URL or ./data/stock_platform.db)",
    )
    p.add_argument(
        "--track-brief",
        type=Path,
        default=None,
        help="Track a brief JSON file's recommendation boards as pre-market hits",
    )
    p.add_argument(
        "--track-json",
        type=Path,
        default=None,
        help="Track a JSON array of {code,name,category} as hits",
    )
    p.add_argument(
        "--session",
        default=PRE_MARKET,
        choices=list(HIT_SESSION_TYPES),
        help="Session for tracking / query filter (default pre_market)",
    )
    p.add_argument(
        "--boards",
        default="quality",
        help="Comma list of board slugs for --track-brief (default quality)",
    )
    p.add_argument("--report", action="store_true", help="Print markdown report (default action)")
    p.add_argument("--summary", action="store_true", help="Print the three cumulative views")
    p.add_argument("--details", action="store_true", help="Print hit detail rows")
    p.add_argument("--code", default=None, help="Filter details by code")
    p.add_argument("--category", default=None, help="Filter details by category")
    p.add_argument("--start", default=None, help="Details pick_date >= (YYYY-MM-DD)")
    p.add_argument("--end", default=None, help="Details pick_date <= (YYYY-MM-DD)")
    p.add_argument("--limit", type=int, default=None, help="Cap rows")
    p.add_argument("--top", type=int, default=10, help="Report/detail rows per view")
    p.add_argument("--asof", default=None, help="Reference day for cycle-window views")
    p.add_argument("--json-out", type=Path, help="Write the structured payload JSON")
    args = p.parse_args(argv)

    repo = open_hit_repository(args.db)
    out: dict[str, Any] = {
        "dbPath": str(getattr(repo, "_path", args.db)),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }

    did_track = False
    if args.track_brief is not None:
        brief = json.loads(Path(args.track_brief).read_text(encoding="utf-8"))
        boards = tuple(b.strip() for b in str(args.boards).split(",") if b.strip())
        tracked = track_brief_hits(repo, brief, boards=boards, session_type=args.session)
        out["tracked"] = tracked
        did_track = True
    if args.track_json is not None:
        entries = json.loads(Path(args.track_json).read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise SystemExit("--track-json must be a JSON array of {code,name,category}")
        tracked = repo.record_many(entries, session_type=args.session)
        out["tracked"] = tracked
        did_track = True

    want_summary = args.summary or (not did_track and not args.details and not args.report)
    if want_summary:
        out["snapshot"] = hit_tracking_snapshot(repo, asof=args.asof, cycle_top_n=args.top)
    if args.details:
        out["details"] = repo.details(
            code=args.code,
            session_type=args.session if args.session else None,
            category=args.category,
            start=args.start,
            end=args.end,
            limit=args.limit or args.top,
        )
    if args.report or (not did_track and not args.summary and not args.details):
        out["report"] = format_hit_report(repo, asof=args.asof, top_n=args.top)

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")

    if "report" in out:
        print(out["report"])
    else:
        print(text)

    if "snapshot" in out:
        snap = out["snapshot"]
        print(
            "pre_market={p}/{pc} post_market={q}/{qc} pre_market_in_cycle={c}/{cc}".format(
                p=snap["pre_market"]["cumulativeHits"],
                pc=snap["pre_market"]["codeCount"],
                q=snap["post_market"]["cumulativeHits"],
                qc=snap["post_market"]["codeCount"],
                c=snap["pre_market_in_cycle"]["cycleHits"],
                cc=snap["pre_market_in_cycle"]["codeCount"],
            ),
            file=sys.stderr,
        )
    if did_track:
        print(
            f"tracked recorded={out['tracked']['recorded']} "
            f"skipped={out['tracked']['skipped']} session={args.session}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
