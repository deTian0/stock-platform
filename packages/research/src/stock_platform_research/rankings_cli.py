"""CLI: split a scored cross-section into the five ranking boards (``X2``).

Usage::

    stock-platform-rankings --panel briefs/2026-09-03/panel.csv --asof 2026-09-03
    stock-platform-rankings --panel panel.csv --holdings book.json --md boards.md
    stock-platform-rankings --panel panel.csv --csv boards.csv --json boards.json

``--panel`` may be a raw feature panel (no ``composite_score``) or an already
scored one; scoring uses :func:`stock_platform_research.batch.score_cross_section`
(the same call the brief makes), so CLI and pipeline cannot disagree.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .batch import score_cross_section
from .position_review_cli import load_holdings
from .rankings import (
    RankingConfig,
    build_rankings,
    format_rankings_markdown,
    rankings_to_rows,
)


def _load_panel(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    return df


def _scored(df: pd.DataFrame, *, value_factor: bool, reversal_q: float) -> pd.DataFrame:
    if "composite_score" in df.columns and df["composite_score"].notna().any():
        return df.sort_values("composite_score", ascending=False)
    return score_cross_section(
        df,
        value_factor=value_factor,
        reversal_q=reversal_q,
        apply_gates=True,
        top_n=None,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Ranking boards: ②A 质量榜 / ②B 短线榜 / ③A 持仓 / ③B 操作建议 / ③C 观察名单"
    )
    p.add_argument("--panel", required=True, help="panel CSV (raw features or already scored)")
    p.add_argument("--asof", default=None, help="as-of trade date (YYYY-MM-DD)")
    p.add_argument("--holdings", default=None, help="holdings JSON (list or {'holdings': [...]})")
    p.add_argument("--quality-top-n", type=int, default=10)
    p.add_argument("--short-top-n", type=int, default=5)
    p.add_argument("--watchlist-top-n", type=int, default=23)
    p.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="composite_score floor (0-1 percentile scale; 0 = disabled)",
    )
    p.add_argument("--value-factor", action="store_true")
    p.add_argument("--reversal-q", type=float, default=0.30)
    p.add_argument("--md", default=None, help="write markdown to this path")
    p.add_argument("--csv", default=None, help="write flattened rows to this path")
    p.add_argument("--json", default=None, help="write the full payload to this path")
    p.add_argument("--quiet", action="store_true", help="suppress stdout markdown")
    args = p.parse_args(argv)

    panel = _load_panel(args.panel)
    holdings: list[dict[str, Any]] = []
    if args.holdings:
        holdings = load_holdings(args.holdings)

    cfg = RankingConfig(
        quality_top_n=args.quality_top_n,
        short_term_top_n=args.short_top_n,
        watchlist_top_n=args.watchlist_top_n,
        min_composite_score=args.min_score,
    )
    scored = _scored(panel, value_factor=args.value_factor, reversal_q=args.reversal_q)
    payload = build_rankings(
        scored,
        holdings=holdings,
        config=cfg,
        panel=panel,
        asof=args.asof,
    )

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.csv:
        rows = rankings_to_rows(payload)
        out_csv = Path(args.csv)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out_csv, index=False)
    md = format_rankings_markdown(payload)
    if args.md:
        out_md = Path(args.md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md, encoding="utf-8")
    if not args.quiet:
        print(md, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
