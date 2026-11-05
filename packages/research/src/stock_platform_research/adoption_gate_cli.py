"""CLI: 策略采纳闸门 over a **read-only** engine ``market.db`` (milestone ``Y1``).

    stock-platform-strategy-adoption --years 1 --windows 3
    stock-platform-strategy-adoption --start 2024-01-01 --end 2026-09-08

Reads ``daily_price`` (bars) and ``fundamentals.industry`` (the ``code → industry``
map) from the path in ``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``) — both
**read-only** — then runs baseline + every registered candidate through the shared
engine on each out-of-sample window and writes the verdict report to
``data/strategy/adoption_gate.{json,md,html}``.

Exit codes: ``0`` report produced · ``2`` no bars / not evaluable · ``1`` bad args.
The report only **recommends** — it never changes a production default.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from .adoption_gate import (
    BASELINE_SPEC,
    CANDIDATE_REGISTRY,
    DEFAULT_ADOPTION_OUT_DIR,
    DEFAULT_CANDIDATES,
    DEFAULT_WINDOW_COUNT,
    DEFAULT_WINDOW_WARMUP_DAYS,
    DEFAULT_WINDOW_YEARS,
    SHADOW_CANDIDATE_SPEC,
    AdoptionRule,
    CandidateSpec,
    build_windows,
    evaluate_adoption,
    render_adoption_markdown,
)
from .backtest import UNIVERSES
from .backtest_cli import (
    ENV_DB,
    filter_universe,
    load_engine_bars,
    load_engine_industry,
    load_engine_names,
)
from .book_replay import ReplayParams
from .dotenv import load_dotenv
from .shadow_board.backtest import prepare_shadow_frame


def _last_bar_date(db_path: str) -> str | None:
    """Read-only ``SELECT MAX(date)`` — avoids loading 8.8M rows just for the anchor."""
    uri = "file:%s?mode=ro" % str(db_path).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute("SELECT MAX(date) FROM daily_price").fetchone()
    finally:
        con.close()
    return str(row[0])[:10] if row and row[0] else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-strategy-adoption",
        description="策略采纳闸门：已验证改进的多窗口样本外裁决（SIMULATE）。",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--start", default=None, help="固定起点 → 单窗口 [start, end]（给定则忽略 --years/--windows）")
    p.add_argument("--end", default=None, help="锚定终点 YYYY-MM-DD（默认：库内最后交易日）")
    p.add_argument("--years", type=int, default=DEFAULT_WINDOW_YEARS, help="滚动窗口长度（年）")
    p.add_argument("--windows", type=int, default=DEFAULT_WINDOW_COUNT, help="滚动窗口个数（互不重叠）")
    p.add_argument("--universe", choices=list(UNIVERSES), default="stock", help="stock (默认) | etf | all")
    p.add_argument("--candidates", default="", help="逗号分隔的候选名（默认全部）；可用 'none' 只看基线")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--min-sharpe-margin", type=float, default=None, help="候选夏普须高于基线的最小边际")
    p.add_argument("--max-drawdown-tolerance", type=float, default=None, help="允许的回撤恶化幅度")
    p.add_argument("--max-winrate-drop", type=float, default=None, help="允许的胜率下滑幅度")
    p.add_argument("--min-trades", type=int, default=None, help="单窗最少成交笔数")
    p.add_argument("--any-window", action="store_true", help="多数窗口通过即采纳（默认要求全部通过）")
    p.add_argument("--out-dir", default=DEFAULT_ADOPTION_OUT_DIR, help=f"输出目录（默认 {DEFAULT_ADOPTION_OUT_DIR}）")
    p.add_argument("--json", action="store_true", help="额外打印完整 JSON 报告")
    p.add_argument("--json-out", default=None, help="JSON 输出路径（默认 <out-dir>/adoption_gate.json）")
    p.add_argument("--out", default=None, help="Markdown 输出路径（默认 <out-dir>/adoption_gate.md）")
    p.add_argument("--html-out", default=None, help="HTML 输出路径（默认 <out-dir>/adoption_gate.html）")
    p.add_argument("--no-write", action="store_true", help="只打印，不落盘")
    p.add_argument(
        "--include-shadow",
        action="store_true",
        help=(
            "额外把多策略影子终榜（ADR 0093）作为 Y1 候选加入裁决（逐日 Round1，较慢）；"
            "默认不含，不影响既有候选的裁决结果"
        ),
    )
    return p


def _resolve_candidates(raw: str, *, include_shadow: bool = False) -> list[CandidateSpec]:
    raw = (raw or "").strip()
    if not raw:
        out = list(DEFAULT_CANDIDATES)
    elif raw.lower() == "none":
        out = []
    else:
        names = [n.strip() for n in raw.split(",") if n.strip()]
        unknown = [n for n in names if n not in CANDIDATE_REGISTRY]
        if unknown:
            raise SystemExit(
                f"unknown candidate(s): {', '.join(unknown)} — available: "
                f"{', '.join(CANDIDATE_REGISTRY)}"
            )
        out = [CANDIDATE_REGISTRY[n] for n in names]
    if include_shadow:
        out = [*out, SHADOW_CANDIDATE_SPEC]
    return out


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # CLI == .bat behaviour (P0-2)
    args = build_parser().parse_args(argv)
    db = (args.db or "").strip()
    if not db:
        raise SystemExit(
            f"no market.db: pass --db or set {ENV_DB} "
            "(point it at a-stock-engine/data_cache/market.db, read-only)."
        )
    if not Path(db).is_file():
        raise SystemExit(f"market.db not found: {db}")

    end_date = (args.end or "").strip() or _last_bar_date(db)
    if not end_date:
        print("[fail] daily_price has no rows", file=sys.stderr)
        return 2

    if args.start:
        windows = [{"label": "w1", "start": str(args.start)[:10], "end": end_date}]
    else:
        windows = build_windows(end_date, years=args.years, count=args.windows)

    try:
        load_start = (
            date.fromisoformat(windows[0]["start"]) - timedelta(days=DEFAULT_WINDOW_WARMUP_DAYS)
        ).isoformat()
    except ValueError as exc:
        raise SystemExit(f"bad --start: {exc}") from exc

    print(f"[db] {db}", file=sys.stderr)
    print(
        f"[windows] {len(windows)} × {args.years}y  " +
        " | ".join(f"{w['label']}:{w['start']}~{w['end']}" for w in windows),
        file=sys.stderr,
    )
    bars = filter_universe(
        load_engine_bars(db, start=load_start, end=end_date, with_amount=args.include_shadow)
    )
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()} (warmup from {load_start})", file=sys.stderr)
    if bars.empty:
        print("[fail] no bars in range", file=sys.stderr)
        return 2

    try:
        industry = load_engine_industry(db)
    except KeyError as exc:
        print(f"[warn] industry unavailable ({exc}); neutralization will de-mean globally", file=sys.stderr)
        industry = None
    print(f"[industry] codes={len(industry or {})}", file=sys.stderr)

    # ``prepare_shadow_frame`` is a superset of ``prepare_book_frame`` (adds
    # ``amount``/``rs20`` on top of the same features + universe + window
    # filter), so the screener candidates run unchanged whether or not
    # ``--include-shadow`` is set — one frame for every candidate (``X4``).
    feats = prepare_shadow_frame(bars, universe=args.universe, industry_map=industry)
    if feats.empty:
        print("[fail] empty feature frame", file=sys.stderr)
        return 2

    _defaults = AdoptionRule()
    rule = AdoptionRule(
        min_sharpe_margin=(
            args.min_sharpe_margin if args.min_sharpe_margin is not None else _defaults.min_sharpe_margin
        ),
        max_drawdown_tolerance=(
            args.max_drawdown_tolerance
            if args.max_drawdown_tolerance is not None
            else _defaults.max_drawdown_tolerance
        ),
        max_winrate_drop=(
            args.max_winrate_drop if args.max_winrate_drop is not None else _defaults.max_winrate_drop
        ),
        min_trades=int(args.min_trades) if args.min_trades is not None else _defaults.min_trades,
        require_all_windows=not args.any_window,
    )
    params = ReplayParams(initial_capital=args.initial_capital, max_positions=args.max_positions)
    candidates = _resolve_candidates(args.candidates, include_shadow=args.include_shadow)
    if args.include_shadow:
        names = load_engine_names(db)
        print(f"[shadow] names={len(names)}（纳入影子终榜候选，逐日 Round1 较慢）", file=sys.stderr)
        from dataclasses import replace as _dc_replace

        candidates = [
            _dc_replace(c, name_map=names) if c.engine == "shadow" else c for c in candidates
        ]

    payload = evaluate_adoption(
        feats,
        baseline=BASELINE_SPEC,
        candidates=candidates,
        windows=windows,
        rule=rule,
        params=params,
        generated_at=date.today().isoformat(),
    )
    if not payload.get("ok"):
        print(f"[fail] {payload.get('reason')}", file=sys.stderr)
        return 2

    payload["universe"] = args.universe
    payload["years"] = args.years
    payload["db"] = str(db)
    md = render_adoption_markdown(payload)
    print(md)

    if payload.get("recommended"):
        print(f"\n[suggest] 建议采纳：{', '.join(payload['recommended'])}", file=sys.stderr)
    else:
        print("\n[suggest] 无候选通过闸门 —— 维持生产基线。", file=sys.stderr)

    if not args.no_write:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = Path(args.json_out) if args.json_out else out_dir / "adoption_gate.json"
        md_path = Path(args.out) if args.out else out_dir / "adoption_gate.md"
        html_path = Path(args.html_out) if args.html_out else out_dir / "adoption_gate.html"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")
        try:
            from .report_html import render_report_html

            html_path.write_text(
                render_report_html(
                    md,
                    title="策略采纳闸门",
                    badge="ADOPTION",
                    source=str(db),
                    generated_at=str(payload.get("generatedAt") or ""),
                ),
                encoding="utf-8",
            )
        except Exception:  # HTML is cosmetic; never let it break the report.
            pass
        print(f"[write] {json_path} | {md_path} | {html_path}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
