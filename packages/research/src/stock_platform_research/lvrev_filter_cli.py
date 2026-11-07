"""CLI: stock-platform-lvrev-filter — entry-filter / cooldown offline compare."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from .dotenv import load_dotenv
from .lvrev_filter_experiment import VARIANTS, compare_lvrev_filters


def _pct(x: object) -> str:
    if x is None:
        return "—"
    try:
        return f"{100.0 * float(x):+.2f}%"
    except (TypeError, ValueError):
        return "—"


def render_markdown(payload: dict) -> str:
    lines = [
        "# lvrev 候选过滤 / 冷静期实验",
        "",
        f"> 计划：`{payload.get('plan')}` · 区间 {payload.get('start')}~{payload.get('end')}",
        "",
        "## 全区间",
        "",
        "| 臂 | 总收益 | MaxDD | 夏普 | 胜率 | 成交 | 判定 |",
        "|----|--------|-------|------|------|------|------|",
    ]
    b = (payload.get("baseline") or {}).get("metrics") or {}
    lines.append(
        f"| baseline | {_pct(b.get('total_return'))} | {_pct(b.get('max_drawdown'))} | "
        f"{b.get('sharpe')} | {_pct(b.get('win_rate'))} | "
        f"{b.get('n_trades', (payload.get('baseline') or {}).get('review', {}).get('settledCount', '—'))} | — |"
    )
    for vid, block in (payload.get("comparisons") or {}).items():
        m = block.get("metrics") or {}
        c = block.get("criteria") or {}
        verdict = "通过" if c.get("passed") else "不通过"
        lines.append(
            f"| {vid} | {_pct(m.get('total_return'))} | {_pct(m.get('max_drawdown'))} | "
            f"{m.get('sharpe')} | {_pct(m.get('win_rate'))} | "
            f"{m.get('n_trades', (block.get('review') or {}).get('settledCount', '—'))} | **{verdict}** |"
        )
    lines.append("")
    lines.append("## 标准明细")
    lines.append("")
    for vid, block in (payload.get("comparisons") or {}).items():
        c = block.get("criteria") or {}
        a, bcrit, cc, d = c.get("a") or {}, c.get("b") or {}, c.get("c") or {}, c.get("d") or {}
        lines.append(
            f"- **{vid}**：passed={c.get('passed')} · "
            f"(a)夏普年 {a.get('sharpe_wins')}/{a.get('needed')} ok={a.get('ok')} · "
            f"(b)集中度 ok={bcrit.get('ok')} max={bcrit.get('max_contribution')} · "
            f"(c)Y1 {cc.get('variant_pass_windows')}≥{cc.get('baseline_pass_windows')} "
            f"ok={cc.get('ok')} · "
            f"(d)MaxDD ok={d.get('ok')} "
            f"({d.get('variant_max_drawdown')} vs {d.get('baseline_max_drawdown')})"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        prog="stock-platform-lvrev-filter",
        description="lvrev 入场过滤 / 冷静期离线对照；默认关，不改出厂。",
    )
    from .backtest_cli import ENV_DB

    p.add_argument("--db", default=None, help=f"只读 market.db（或 env {ENV_DB}）")
    p.add_argument("--start", default="2021-01-04")
    p.add_argument("--end", default=None)
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--variants", default=",".join(VARIANTS))
    p.add_argument("--skip-y1", action="store_true")
    p.add_argument("--out-dir", default="local/lvrev_filter")
    args = p.parse_args(argv)

    from .adoption_gate_cli import _last_bar_date
    from .backtest_cli import (
        ENV_DB as _ENV,
        filter_universe,
        load_engine_bars,
        load_engine_industry,
        load_engine_names,
    )
    from .book_replay import ReplayParams
    from .shadow_board.backtest import prepare_shadow_frame

    db = (args.db or os.environ.get(_ENV, "")).strip()
    if not db or not Path(db).is_file():
        print(f"[fail] market.db 不可用：{db or '未设置 ' + _ENV}", file=sys.stderr)
        return 2
    end = (args.end or "").strip() or _last_bar_date(db)
    if not end:
        print("[fail] daily_price 无数据", file=sys.stderr)
        return 2
    variants = [v.strip() for v in str(args.variants).split(",") if v.strip()]
    bad = [v for v in variants if v not in VARIANTS]
    if bad:
        print(f"[fail] 未知变体 {bad}；可选 {list(VARIANTS)}", file=sys.stderr)
        return 2

    load_start = (date.fromisoformat(args.start) - timedelta(days=180)).isoformat()
    print(f"[db] {db}  区间 {args.start}~{end}（预热自 {load_start}）", file=sys.stderr)
    bars = filter_universe(load_engine_bars(db, start=load_start, end=end, with_amount=True))
    if bars.empty:
        print("[fail] 区间内无行情", file=sys.stderr)
        return 2
    try:
        industry = load_engine_industry(db)
    except KeyError:
        industry = None
    names = load_engine_names(db)
    feats = prepare_shadow_frame(bars, start=args.start, end=end, industry_map=industry)
    print(f"[feats] rows={len(feats)} days={feats['trade_date'].nunique()}", file=sys.stderr)

    from .benchmark import load_benchmark_closes

    index_close, bench_block = load_benchmark_closes(db, args.start, end, names=names)

    payload = compare_lvrev_filters(
        feats,
        variants=variants,
        params=ReplayParams(
            initial_capital=args.initial_capital,
            max_positions=args.max_positions,
        ),
        run_y1=not args.skip_y1,
        index_close=index_close,
        benchmark=bench_block,
    )
    payload["db"] = str(db)
    payload["start"] = args.start
    payload["end"] = end
    md = render_markdown(payload)
    print(md)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lvrev_filter.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "lvrev_filter.md").write_text(md, encoding="utf-8")
    print(f"[write] {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
