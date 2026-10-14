"""CLI ``stock-platform-performance-proxy``：长窗回测 → 代理台账 → 真实/代理并排报告（``R4``）。

Examples::

    # 用共享引擎（lvrev 选股侧）跑最近一年，产出代理台账 + 报告
    stock-platform-performance-proxy --db D:/.../market.db --years 1

    # 用已归档的 picks 账本 / briefs 回放（走 picks 入口，同引擎）
    stock-platform-performance-proxy --db D:/.../market.db --ledger data/picks_ledger.jsonl

    # 指定窗口 + 只打印不落盘
    stock-platform-performance-proxy --db D:/.../market.db --start 2025-06-01 --end 2026-09-30 --no-write

产出（默认写 ``data/performance/``）：
``proxy_ledger.jsonl``（代理台账）· ``proxy_vs_real.json`` · ``proxy_vs_real.md`` · ``proxy_vs_real.html``。

读 ``market.db`` 只读（``mode=ro``），绝不写库；真实台账只读。SIMULATE 非投资建议。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from .backtest import UNIVERSES, run_portfolio_backtest
from .backtest_cli import ENV_DB, filter_universe, load_engine_bars
from .dotenv import load_dotenv
from .performance import default_performance_log_path
from .performance_proxy import (
    DEFAULT_PROXY_OUT_DIR,
    build_proxy_view,
    default_proxy_log_path,
    render_proxy_markdown,
    trades_to_decision_rows,
    write_proxy_ledger,
)
from .picks_backtest import load_picks_ledger, run_picks_backtest
from .picks_backtest_cli import load_briefs_picks


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-performance-proxy",
        description="长窗回测 → 绩效代理台账，与真实台账并排（分栏、禁止混算）。",
    )
    p.add_argument("--db", default=None, help=f"引擎 market.db（默认 ${ENV_DB}，只读）")
    p.add_argument("--start", default=None, help="回测起点 YYYY-MM-DD（默认：end 往前 years 年）")
    p.add_argument("--end", default=None, help="回测终点 YYYY-MM-DD（默认：行情库最后一日）")
    p.add_argument("--years", type=int, default=1, help="未给 --start 时的窗口长度（年，默认 1）")
    p.add_argument("--ledger", default=None, help="picks 账本 JSONL（给了就走 picks 入口回放）")
    p.add_argument("--briefs-dir", default=None, help="briefs/ 目录（从 ②A 头部取推荐）")
    p.add_argument(
        "--universe",
        choices=list(UNIVERSES),
        default="stock",
        help="可交易集：stock（默认，与选股基线一致）| etf | all",
    )
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument("--max-picks-per-day", type=int, default=8)
    p.add_argument("--min-hold", type=int, default=45)
    p.add_argument("--stop-loss", type=float, default=8.0)
    p.add_argument("--min-pick-score", type=float, default=0.80, help="仅选股侧使用")
    p.add_argument("--real-log", default=None, help="真实台账 JSONL（默认 STOCK_PLATFORM_PERFORMANCE_LOG）")
    p.add_argument("--proxy-log", default=None, help="代理台账输出路径（默认 data/performance_proxy.jsonl）")
    p.add_argument("--out-dir", type=Path, default=None, help=f"报告输出目录（默认 {DEFAULT_PROXY_OUT_DIR}）")
    p.add_argument("--recent-days", type=int, default=5, help="per-day 方向准确率窗口（默认 5）")
    p.add_argument("--no-write", action="store_true", help="只打印，不写文件")
    p.add_argument("--json", action="store_true", help="额外打印完整 payload JSON")
    return p


def _resolve_window(
    bars, *, start: str | None, end: str | None, years: int
) -> tuple[str | None, str | None]:
    """解析回测窗口：显式优先；否则 end=行情最后一日、start=end − years 年。"""
    if start:
        return start, end
    dates = bars["date"]
    if len(dates) == 0:
        return start, end
    last = str(dates.max())[:10]
    resolved_end = end or last
    try:
        anchor = date.fromisoformat(resolved_end)
    except ValueError:
        anchor = date.fromisoformat(last)
    resolved_start = (anchor - timedelta(days=max(1, int(years)) * 365)).isoformat()
    return resolved_start, end


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    import os

    db = (args.db or os.environ.get(ENV_DB) or "").strip()
    if not db:
        raise SystemExit(f"no market.db: pass --db or set {ENV_DB}")
    if not Path(db).is_file():
        raise SystemExit(f"market.db not found: {db}")

    print(f"[db] {db}", file=sys.stderr)
    bars = filter_universe(load_engine_bars(db))
    if bars.empty:
        raise SystemExit(f"no bars loaded from {db}")
    start, end = _resolve_window(bars, start=args.start, end=args.end, years=args.years)
    print(
        f"[window] start={start} end={end or '(last)'} rows={len(bars)} codes={bars['code'].nunique()}",
        file=sys.stderr,
    )

    common = dict(
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        max_picks_per_day=args.max_picks_per_day,
        min_hold=args.min_hold,
        stop_loss=args.stop_loss,
        universe=args.universe,
        start=start,
        end=end,
    )

    entry_source: str
    if args.ledger:
        picks = load_picks_ledger(args.ledger)
        if not picks:
            raise SystemExit(f"no pick rows in ledger: {args.ledger}")
        entry_source = f"ledger:{args.ledger}"
        res = run_picks_backtest(picks, bars, **common)
    elif args.briefs_dir:
        picks = load_briefs_picks(args.briefs_dir)
        if not picks:
            raise SystemExit(f"no pick rows in briefs: {args.briefs_dir}")
        entry_source = f"briefs:{args.briefs_dir}"
        res = run_picks_backtest(picks, bars, **common)
    else:
        entry_source = "screener:lvrev"
        res = run_portfolio_backtest(bars, min_pick_score=args.min_pick_score, **common)

    trades = res.get("trades") or []
    rows = trades_to_decision_rows(trades, equity_curve=res.get("equity_curve"))
    print(
        "[replay] ok={} trades={} proxyRows={}".format(
            res.get("ok"), len(trades), len(rows)
        ),
        file=sys.stderr,
    )
    if not res.get("ok"):
        print(f"[fail] {res.get('reason')}", file=sys.stderr)

    proxy_path = Path(args.proxy_log) if args.proxy_log else default_proxy_log_path()
    real_path = Path(args.real_log) if args.real_log else default_performance_log_path()

    proxy_meta = {
        "entrySource": entry_source,
        "universe": args.universe,
        "start": start,
        "end": end,
        "initialCapital": args.initial_capital,
        "maxPositions": args.max_positions,
        "metrics": res.get("metrics") or {},
    }
    view = build_proxy_view(
        real_path=real_path,
        proxy_entries=rows,
        proxy_meta=proxy_meta,
        recent_days=max(1, int(args.recent_days)),
    )
    view["proxy"]["ledgerPath"] = str(proxy_path)
    md = render_proxy_markdown(view)

    if not args.no_write:
        out_dir = Path(args.out_dir) if args.out_dir else Path(DEFAULT_PROXY_OUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_proxy_ledger(proxy_path, rows)
        json_path = out_dir / "proxy_vs_real.json"
        md_path = out_dir / "proxy_vs_real.md"
        html_path = out_dir / "proxy_vs_real.html"
        json_path.write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")
        try:
            from .report_html import render_report_html

            html_path.write_text(
                render_report_html(
                    md,
                    title="绩效代理台账（代理 vs 真实）",
                    badge="PROXY",
                    generated_at=str(view.get("generatedAt") or ""),
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — HTML 是可选锦上添花，绝不拖垮报告
            pass
        print(f"[out] {out_dir} (ledger={proxy_path})", file=sys.stderr)

    print(md)
    adeq = view.get("sampleAdequacy") or {}
    print(
        "proxy-vs-real realSettled={r} proxySettled={p} threshold={t}".format(
            r=adeq.get("realSettled"),
            p=adeq.get("proxySettled"),
            t=adeq.get("threshold"),
        ),
        file=sys.stderr,
    )
    if args.json:
        print(json.dumps(view, ensure_ascii=False, default=str))
    return 0 if res.get("ok") else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
