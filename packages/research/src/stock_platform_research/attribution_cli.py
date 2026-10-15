"""CLI: 收益归因 / 负收益根因诊断 over a **read-only** engine ``market.db`` (milestone ``Y3``).

    stock-platform-attribution --years 1
    stock-platform-attribution --start 2025-10-14 --end 2026-10-14 --score-floor 0.80

Loads bars from the path in ``STOCK_PLATFORM_ENGINE_MARKET_DB`` (or ``--db``) —
**read-only** — extracts the benchmark series from the same frame, then:

1. builds the **signal panel** (per-session ``score_lvrev`` + ``apply_entry_gates``,
   the same scorer the production entry provider uses) with forward (excess) returns;
2. replays the **production baseline book** once for the cost / payoff /
   concentration blocks;
3. runs the pure :func:`attribution.diagnose` over those blocks.

Writes ``data/strategy/attribution.{json,md,html}``.

Exit codes: ``0`` report produced · ``2`` no bars / not evaluable · ``1`` bad args.
The report only **attributes** — it never changes a production default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from .attribution import (
    CONCENTRATION_KEYS,
    DEFAULT_ATTRIBUTION_OUT_DIR,
    DEFAULT_HORIZONS,
    DEFAULT_REFERENCE_HORIZON,
    DEFAULT_SCORE_BUCKETS,
    DEFAULT_SCORE_FLOOR,
    BASIS_EXCESS,
    BASIS_RAW,
    MIN_MEANINGFUL_SAMPLE,
    SET_GATED,
    SET_PICKS,
    build_signal_panel,
    concentration,
    cost_drag,
    diagnose,
    horizon_curve,
    payoff_profile,
    render_attribution_markdown,
    score_curve,
)
from .backtest import UNIVERSES, prepare_book_frame
from .backtest_cli import ENV_DB, filter_universe, load_engine_bars, load_engine_industry
from .book_replay import ReplayParams
from .dotenv import load_dotenv
from .neutralization_ab import run_neutralization_book
from .performance import resolve_benchmark_symbol

#: Extra calendar span loaded *before* the window start so ``ma60`` is warm.
WARMUP_DAYS = 180


def _resolve_benchmark_code(raw: str) -> str:
    """``'000905'`` → ``'000905.SZ'``（引擎库的指数代码带 ``.SZ`` 后缀）。"""
    code = (raw or "").strip()
    if not code:
        code = resolve_benchmark_symbol()
    return code if "." in code else f"{code}.SZ"


def _last_bar_date(db_path: str) -> str | None:
    """Read-only ``SELECT MAX(date)`` — avoids loading 8.8M rows just for the anchor."""
    import sqlite3

    uri = "file:%s?mode=ro" % str(db_path).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute("SELECT MAX(date) FROM daily_price").fetchone()
    finally:
        con.close()
    return str(row[0])[:10] if row and row[0] else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-attribution",
        description="收益归因 / 负收益根因诊断：信号边缘 + 持有期 + 成本 + 集中度（SIMULATE）。",
    )
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db path (default: ${ENV_DB})")
    p.add_argument("--start", default=None, help="窗口起点 YYYY-MM-DD（默认：end − years 年）")
    p.add_argument("--end", default=None, help="窗口终点 YYYY-MM-DD（默认：库内最后交易日）")
    p.add_argument("--years", type=int, default=1, help="窗口长度（年，仅当未给 --start）")
    p.add_argument("--universe", choices=list(UNIVERSES), default="stock", help="stock (默认) | etf | all")
    p.add_argument("--benchmark", default="", help=f"基准代码（默认 {resolve_benchmark_symbol()} → 补 .SZ 后缀）")
    p.add_argument("--no-benchmark", action="store_true", help="不给基准：曲线退用裸收益")
    p.add_argument("--score-floor", type=float, default=DEFAULT_SCORE_FLOOR, help="评分闸门（生产默认 0.80）")
    p.add_argument("--horizons", default=",".join(str(k) for k in DEFAULT_HORIZONS), help="持有期（交易日，逗号分隔）")
    p.add_argument("--buckets", type=int, default=DEFAULT_SCORE_BUCKETS, help="评分分位桶数")
    p.add_argument("--reference-horizon", type=int, default=DEFAULT_REFERENCE_HORIZON, help="评分单调性的参照持有期")
    p.add_argument("--min-sample", type=int, default=MIN_MEANINGFUL_SAMPLE, help="每个持有期的样本门槛")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--no-replay", action="store_true", help="跳过基线回放（略过成本/赔率/集中度块）")
    p.add_argument("--out-dir", default=DEFAULT_ATTRIBUTION_OUT_DIR, help=f"输出目录（默认 {DEFAULT_ATTRIBUTION_OUT_DIR}）")
    p.add_argument("--json", action="store_true", help="额外打印完整 JSON 报告")
    p.add_argument("--json-out", default=None, help="JSON 输出路径（默认 <out-dir>/attribution.json）")
    p.add_argument("--out", default=None, help="Markdown 输出路径（默认 <out-dir>/attribution.md）")
    p.add_argument("--html-out", default=None, help="HTML 输出路径（默认 <out-dir>/attribution.html）")
    p.add_argument("--no-write", action="store_true", help="只打印，不落盘")
    return p


def _parse_horizons(raw: str) -> tuple[int, ...]:
    parts = [int(x) for x in str(raw or "").replace(" ", "").split(",") if x.strip()]
    return tuple(sorted({k for k in parts if k > 0})) or DEFAULT_HORIZONS


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
        start_date = str(args.start)[:10]
    else:
        start_date = (date.fromisoformat(end_date) - timedelta(days=int(args.years) * 365)).isoformat()
    try:
        load_start = (date.fromisoformat(start_date) - timedelta(days=WARMUP_DAYS)).isoformat()
    except ValueError as exc:
        raise SystemExit(f"bad --start: {exc}") from exc

    bench_code = "" if args.no_benchmark else _resolve_benchmark_code(args.benchmark)
    horizons = _parse_horizons(args.horizons)
    print(f"[db] {db}", file=sys.stderr)
    print(f"[window] {start_date} ~ {end_date} (warmup from {load_start})", file=sys.stderr)
    print(f"[benchmark] {bench_code or '—'} | horizons={list(horizons)}", file=sys.stderr)

    bars_all = load_engine_bars(db, start=load_start, end=end_date)
    if bars_all.empty:
        print("[fail] no bars in range", file=sys.stderr)
        return 2

    bench = None
    if bench_code:
        match = bars_all[bars_all["code"] == bench_code]
        if not match.empty:
            bench = match[["date", "close"]].copy()
        else:
            print(f"[warn] benchmark {bench_code} not in daily_price → 退用裸收益", file=sys.stderr)
        # The index row must never be scored/gated as a stock.
        bars_all = bars_all[bars_all["code"] != bench_code]

    bars = filter_universe(bars_all)
    print(f"[load] rows={len(bars)} codes={bars['code'].nunique()}", file=sys.stderr)
    if bars.empty:
        print("[fail] no bars in range", file=sys.stderr)
        return 2

    try:
        industry = load_engine_industry(db)
    except KeyError as exc:
        print(f"[warn] industry unavailable ({exc})", file=sys.stderr)
        industry = None

    feats = prepare_book_frame(
        bars, universe=args.universe, start=start_date, end=end_date, industry_map=industry
    )
    if feats.empty:
        print("[fail] empty feature frame", file=sys.stderr)
        return 2
    print(
        f"[feats] rows={len(feats)} days={feats['trade_date'].nunique()} codes={feats['code'].nunique()}",
        file=sys.stderr,
    )

    # --- run the production baseline book once (cost / payoff / concentration) ---
    params = ReplayParams(initial_capital=args.initial_capital, max_positions=args.max_positions)
    trades: list[dict] = []
    if not args.no_replay:
        book = run_neutralization_book(
            feats, neutralize=None, params=params, min_pick_score=float(args.score_floor)
        )
        trades = list(book.get("trades") or [])
        print(f"[replay] n_days={book.get('n_days')} trades={len(trades)}", file=sys.stderr)

    # --- signal panel + blocks ---
    built = build_signal_panel(
        feats,
        benchmark=bench,
        horizons=horizons,
        score_floor=float(args.score_floor),
    )
    panel = built["panel"]
    if panel.empty:
        print("[fail] no gated entries in window", file=sys.stderr)
        return 2
    basis = BASIS_EXCESS if built["benchmarkAvailable"] else BASIS_RAW
    print(
        f"[panel] gated={built['nGated']} picks={built['nPicks']} days={built['nDays']} basis={basis}",
        file=sys.stderr,
    )

    curve_picks = horizon_curve(
        panel, horizons=horizons, basis=basis, which=SET_PICKS, min_sample=int(args.min_sample)
    )
    curve_gated = horizon_curve(
        panel, horizons=horizons, basis=basis, which=SET_GATED, min_sample=int(args.min_sample)
    )
    score = score_curve(
        panel,
        horizon=int(args.reference_horizon),
        buckets=int(args.buckets),
        basis=basis,
        which=SET_GATED,
        min_sample=int(args.min_sample),
    )
    cost = cost_drag(trades)
    payoff = payoff_profile(trades)
    concentrations = [
        concentration(trades, by=key, industry_map=industry, value_field="net_ret")
        for key in CONCENTRATION_KEYS
    ]

    diagnosis = diagnose(
        curve_picks=curve_picks,
        curve_gated=curve_gated,
        score=score,
        cost=cost,
        payoff=payoff,
        concentrations=concentrations,
        realized_hold_days=cost.get("avgHoldDays"),
        reference_horizon=int(args.reference_horizon),
        min_sample=int(args.min_sample),
    )

    payload: dict = {
        "ok": True,
        "generatedAt": date.today().isoformat(),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "db": str(db),
        "universe": args.universe,
        "start": start_date,
        "end": end_date,
        "nDays": int(feats["trade_date"].nunique()),
        "benchmarkSymbol": bench_code or None,
        "benchmarkAvailable": bool(built["benchmarkAvailable"]),
        "scoreFloor": float(args.score_floor),
        "scoreFloorReplay": not args.no_replay,
        "horizons": list(horizons),
        "basis": basis,
        "nGated": built["nGated"],
        "nPicks": built["nPicks"],
        "referenceHorizon": int(args.reference_horizon),
        "curvePicks": curve_picks,
        "curveGated": curve_gated,
        "score": score,
        "cost": cost,
        "payoff": payoff,
        "concentrations": concentrations,
        "diagnosis": diagnosis,
        "metricNote": (
            "面板与生产 screener_entry_provider 同源（score_lvrev + apply_entry_gates）；"
            "picks = 过闸且 composite_score ≥ scoreFloor（候选池，实盘还会按持仓上限取当日头部），"
            "gated = 全部过闸。excess = 个股收益 − 基准同窗口收益。"
            "**口径归属**：边缘类结论走 excess（技能），持有期类结论走 fwd（赚不赚钱）。"
            "末 k 个交易日因截尾样本自然减少。成交侧 gross_ret/net_ret 源自 book_replay，"
            "单位由百分数归一为小数（×0.01）。"
        ),
        "attributionNote": (
            "本报告只出**归因**：不修改任何生产默认档、不写 brief / picks。"
            "候选方向仍须过 Y1 采纳闸门 + 人工签核。"
        ),
        "disclaimer": "收益归因（研究口径）；非投资建议；SIMULATE；不改主路径权重与 picks。",
    }

    md = render_attribution_markdown(payload)
    print(md)

    top = (diagnosis.get("causes") or [{}])[0]
    print(f"\n[diagnose] {top.get('title')}", file=sys.stderr)

    if not args.no_write:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = Path(args.json_out) if args.json_out else out_dir / "attribution.json"
        md_path = Path(args.out) if args.out else out_dir / "attribution.md"
        html_path = Path(args.html_out) if args.html_out else out_dir / "attribution.html"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")
        try:
            from .report_html import render_report_html

            html_path.write_text(
                render_report_html(
                    md,
                    title="收益归因诊断",
                    badge="ATTRIBUTION",
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
