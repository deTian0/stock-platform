"""CLI: score a PIT cross-section CSV for pre-market briefs."""

from __future__ import annotations

import argparse

from .batch import score_cross_section_csv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Score A-share cross-section CSV with lvrev")
    p.add_argument("input_csv", help="Point-in-time cross-section CSV")
    p.add_argument("-o", "--output", help="Optional output CSV path")
    p.add_argument("--top", type=int, default=50, help="Keep top N after gates (default 50)")
    p.add_argument("--value-factor", action="store_true", help="Enable value weights")
    p.add_argument("--reversal-q", type=float, default=0.30)
    args = p.parse_args(argv)

    out = score_cross_section_csv(
        args.input_csv,
        output=args.output,
        value_factor=args.value_factor,
        reversal_q=args.reversal_q,
        top_n=args.top,
    )
    print(f"scored_rows={len(out)}")
    if len(out) and "composite_score" in out.columns:
        head = out.head(min(5, len(out)))
        cols = [c for c in ("code", "symbol", "name", "composite_score") if c in head.columns]
        print(head[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
