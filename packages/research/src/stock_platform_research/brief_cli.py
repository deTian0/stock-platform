"""CLI: build a pre-market TopN brief from a PIT panel CSV or inline score."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .batch import score_cross_section_csv
from .brief import build_premarket_brief, write_brief_csv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build CN pre-market TopN brief (lvrev + gates)")
    p.add_argument("input_csv", help="Point-in-time cross-section CSV (panel columns)")
    p.add_argument("--asof", required=True, help="Signal trade date YYYY-MM-DD")
    p.add_argument("-o", "--output", help="Optional picks CSV path")
    p.add_argument("--json-out", help="Optional brief JSON path")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--value-factor", action="store_true")
    p.add_argument("--reversal-q", type=float, default=0.30)
    args = p.parse_args(argv)

    panel = pd.read_csv(args.input_csv)
    brief = build_premarket_brief(
        asof=args.asof,
        panel=panel,
        top_n=args.top,
        value_factor=args.value_factor,
        reversal_q=args.reversal_q,
    )
    # Also exercise score CSV path for parity with stock-platform-score.
    score_cross_section_csv(
        args.input_csv,
        top_n=args.top,
        value_factor=args.value_factor,
        reversal_q=args.reversal_q,
    )

    if args.output:
        write_brief_csv(brief, args.output)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(brief, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"asof={brief['asof']} picks={len(brief['picks'])} panel={brief['panelSize']}")
    for pick in brief["picks"][:5]:
        print(
            f"  #{pick['rank']} {pick['symbol']} "
            f"score={pick['composite_score']} reason={pick['reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
