"""CLI: lvrev enhancement offline compare (docs/plans/lvrev-enhancement.md).

Read-only ``market.db`` → shared ``book_replay`` → write ``local/`` artefacts.
SIMULATE only; never opens live; never writes the engine DB.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .dotenv import load_dotenv
from .lvrev_enhancement import VARIANTS, compare_lvrev_enhancements


def _pct(x: Any) -> str:
    if x is None:
        return "—"
    return f"{float(x) * 100:.2f}%"


def _num(x: Any, nd: int = 3) -> str:
    if x is None:
        return "—"
    return f"{float(x):.{nd}f}"


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = [
        "# lvrev 增强实验对照",
        "",
        f"- 变体数 N = {payload.get('nVariants')}（多重比较：任一条不满足即不通过）",
        f"- 超额：{'可用' if payload.get('excessAvailable') else '不可用'}（{payload.get('excessReason') or ''}）",
        f"- 环境：{payload.get('environment')} / liveTradingEnabled={payload.get('liveTradingEnabled')}",
        "",
        "## 全区间对照",
        "",
        "| 臂 | 总收益 | 最大回撤 | 夏普 | 胜率 | 年换手 | 成交笔数 | 平均持有日 |",
        "|----|--------|----------|------|------|--------|----------|------------|",
    ]
    base = payload.get("baseline") or {}
    bm = base.get("metrics") or {}
    lines.append(
        f"| lvrev 基线 | {_pct(bm.get('total_return'))} | {_pct(bm.get('max_drawdown'))} | "
        f"{_num(bm.get('sharpe'), 3)} | {_pct(bm.get('win_rate'))} | "
        f"{_num(bm.get('turnover_per_year'), 1)} | {bm.get('n_trades')} | "
        f"{_num(bm.get('avg_hold_days'), 1)} |"
    )
    for vid, block in (payload.get("comparisons") or {}).items():
        m = block.get("metrics") or {}
        crit = block.get("criteria") or {}
        mark = "✓" if crit.get("passed") else "✗"
        lines.append(
            f"| {vid} {mark} | {_pct(m.get('total_return'))} | {_pct(m.get('max_drawdown'))} | "
            f"{_num(m.get('sharpe'), 3)} | {_pct(m.get('win_rate'))} | "
            f"{_num(m.get('turnover_per_year'), 1)} | {m.get('n_trades')} | "
            f"{_num(m.get('avg_hold_days'), 1)} |"
        )
    lines += ["", "## 通过标准判定", ""]
    for vid, block in (payload.get("comparisons") or {}).items():
        c = block.get("criteria") or {}
        lines.append(f"### `{vid}` — {'通过' if c.get('passed') else '不通过'}")
        a, b, cc, d = c.get("a") or {}, c.get("b") or {}, c.get("c") or {}, c.get("d") or {}
        lines.append(
            f"- (a) 分年夏普 ≥ 基线：{a.get('sharpe_wins')}/{a.get('years')} 年 "
            f"（需 ≥ {a.get('needed')}）→ {'过' if a.get('ok') else '不过'}"
        )
        lines.append(
            f"- (b) 单年超额贡献 ≤ 60%：total_ex={_pct(b.get('total_excess'))} "
            f"max={_pct(b.get('max_contribution'))} "
            f"year={b.get('max_contribution_year')} → {'过' if b.get('ok') else '不过'}"
            + (f"（{b.get('reason')}）" if b.get("reason") else "")
        )
        lines.append(
            f"- (c) Y1 通过窗 ≥ 基线：{cc.get('variant_pass_windows')} ≥ "
            f"{cc.get('baseline_pass_windows')} → {'过' if cc.get('ok') else '不过'}"
        )
        lines.append(
            f"- (d) 最大回撤不更深：变体 {_pct(d.get('variant_max_drawdown'))} vs "
            f"基线 {_pct(d.get('baseline_max_drawdown'))} → {'过' if d.get('ok') else '不过'}"
        )
        lines.append("")
        lines.append("| 年份 | 基线收益/回撤/夏普/胜率 | 变体收益/回撤/夏普/胜率 | 夏普≥基线 | 超额贡献 |")
        lines.append("|------|-------------------------|-------------------------|-----------|----------|")
        for row in c.get("by_year") or []:
            bb, vv = row.get("baseline") or {}, row.get("variant") or {}
            lines.append(
                f"| {row.get('year')} | {_pct(bb.get('total_return'))} / {_pct(bb.get('max_drawdown'))} / "
                f"{_num(bb.get('sharpe'), 3)} / {_pct(bb.get('win_rate'))} | "
                f"{_pct(vv.get('total_return'))} / {_pct(vv.get('max_drawdown'))} / "
                f"{_num(vv.get('sharpe'), 3)} / {_pct(vv.get('win_rate'))} | "
                f"{'Y' if row.get('sharpe_ge_baseline') else 'N'} | "
                f"{_pct(row.get('excess_contribution'))} |"
            )
        lines.append("")
    ex = payload.get("excess")
    if ex:
        lines += [
            "## 相对指数超额（仅报告，不进通过标准）",
            "",
            f"- 基准 `{(payload.get('benchmark') or {}).get('symbol')}` "
            f"来源 {(payload.get('benchmark') or {}).get('source') or 'market.db'}；"
            f"区间 {ex.get('start')}~{ex.get('end')}；指数收益 {_pct(ex.get('benchmarkReturn'))}",
            "",
        ]
        years = list((ex.get("benchmarkByYear") or {}).keys())
        lines.append("| 臂 | 全区间超额 | " + " | ".join(years) + " |")
        lines.append("|----|------------|" + "|".join("----" for _ in years) + "|")
        lines.append(
            "| 指数年收益 | — | "
            + " | ".join(_pct((ex.get("benchmarkByYear") or {}).get(y)) for y in years)
            + " |"
        )
        for k, a in (ex.get("arms") or {}).items():
            by = a.get("byYear") or {}
            lines.append(
                f"| {k} | {_pct(a.get('excessReturn'))} | "
                + " | ".join(_pct((by.get(y) or {}).get("excessReturn")) for y in years)
                + " |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        prog="stock-platform-lvrev-enhancement",
        description="lvrev 增强实验离线对照（Round2 / 大势闸 / 退出规则）；默认关，不改出厂。",
    )
    from .backtest_cli import ENV_DB

    p.add_argument("--db", default=None, help=f"只读 market.db（或 env {ENV_DB}）")
    p.add_argument("--start", default="2021-01-04")
    p.add_argument("--end", default=None, help="默认取库内最后交易日")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument(
        "--variants",
        default=",".join(VARIANTS),
        help=f"逗号列表，默认全部：{','.join(VARIANTS)}",
    )
    p.add_argument("--skip-y1", action="store_true", help="跳过 Y1 3×1y（调试用）")
    p.add_argument(
        "--out-dir",
        default="local/lvrev_enhancement",
        help="产物目录（gitignore）",
    )
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
    print(f"[load] rows={len(bars)} names={len(names)} industry={len(industry or {})}", file=sys.stderr)

    feats = prepare_shadow_frame(bars, start=args.start, end=end, industry_map=industry)
    print(f"[feats] rows={len(feats)} days={feats['trade_date'].nunique()}", file=sys.stderr)
    print(f"[run] variants={variants} y1={not args.skip_y1}", file=sys.stderr)

    # ADR 0095: benchmark via the F1 single point (market.db first, verified aux store fallback).
    from .benchmark import load_benchmark_closes

    index_close, bench_block = load_benchmark_closes(db, args.start, end, names=names)
    print(
        f"[bench] {bench_block.get('symbol')} "
        + (
            f"ok（来源 {bench_block.get('source') or 'market.db'}）"
            if index_close
            else f"unavailable：{bench_block.get('reason')}"
        ),
        file=sys.stderr,
    )

    payload = compare_lvrev_enhancements(
        feats,
        variants=variants,
        params=ReplayParams(
            initial_capital=args.initial_capital,
            max_positions=args.max_positions,
        ),
        name_map=names,
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
    # Drop bulky curves from the summary JSON kept for docs; full arms stay in arms.json
    summary = {k: v for k, v in payload.items() if k != "arms"}
    arms_slim = {
        k: {
            "metrics": v["metrics"],
            "final_equity": v["final_equity"],
            "n_days": v["n_days"],
            "tradeCount": v["tradeCount"],
            "equity_curve": v["equity_curve"],
            "trades": v["trades"],
        }
        for k, v in (payload.get("arms") or {}).items()
    }
    (out_dir / "lvrev_enhancement.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "lvrev_enhancement_arms.json").write_text(
        json.dumps(arms_slim, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "lvrev_enhancement.md").write_text(md, encoding="utf-8")
    print(f"[write] {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
