"""CLI ``stock-platform-shadow-board`` — multi-strategy shadow Final Board (ADR 0093)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..dotenv import load_dotenv
from .ledger import default_shadow_dir
from .pipeline import run_shadow_board


def _load_universe(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [dict(r) for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("universe", "items", "rows", "candidates"):
            block = raw.get(key)
            if isinstance(block, list):
                return [dict(r) for r in block if isinstance(r, dict)]
    raise SystemExit(f"无法解析宇宙 JSON（需 list 或含 universe/items）: {path}")


def _render_summary(payload: dict[str, Any]) -> str:
    board = payload.get("finalBoard") or []
    lines = [
        f"# 影子 Final Board（{payload.get('asof')}）",
        "",
        f"- 状态：`{payload.get('status')}`",
        f"- 席位：{len(board)}（空板合法）",
        f"- 绩效：excludedFromPerformance={payload.get('excludedFromPerformance')}",
        f"- 落盘：{payload.get('ledgerPath') or '（未写）'}",
        "",
    ]
    if not board:
        lines.append("（空板 — 硬闸后无入选，不是缺陷）")
        return "\n".join(lines)
    lines.append("| 代码 | 名称 | 学校 | 得分 | 持有期 |")
    lines.append("|------|------|------|------|--------|")
    for row in board:
        lines.append(
            f"| {row.get('code')} | {row.get('name')} | {row.get('school')} | "
            f"{float(row.get('score') or 0):.3f} | {row.get('holdingPeriod')} |"
        )
    return "\n".join(lines)


def _index_close(db: str, start: str, end: str, code: str = "000300.SH") -> dict[str, float]:
    """Read-only benchmark closes from ``daily_price``; empty when the index is absent."""
    import sqlite3

    uri = "file:%s?mode=ro" % str(db).replace("\\", "/")
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            "SELECT date, close FROM daily_price WHERE code=? AND date>=? AND date<=?",
            (code, start, end),
        ).fetchall()
    finally:
        con.close()
    return {str(d)[:10]: float(c) for d, c in rows if c is not None}


def _parse_s1_scale(text: str | None) -> dict[str, float] | None:
    """``"1,0.5,0"`` → ``{strong, mid, weak, unknown=weak}``; ``None`` → module default."""
    if not text:
        return None
    parts = [float(x) for x in str(text).split(",")]
    if len(parts) != 3 or any(not (0.0 <= v <= 1.0) for v in parts):
        raise SystemExit(f"--s1-scale 需要 3 个 0~1 系数（强,中,弱），得到：{text!r}")
    return {"strong": parts[0], "mid": parts[1], "weak": parts[2], "unknown": parts[2]}


def _s1_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    """Factory ``pick`` passes nothing, so the call is exactly the pre-knob one."""
    if args.s1_mode == "pick":
        return {}
    out: dict[str, Any] = {"s1_mode": args.s1_mode, "s1_gate_weak": args.s1_gate_weak}
    scale = _parse_s1_scale(args.s1_scale)
    if scale is not None:
        out["s1_scale"] = scale
    return out


def _run_backtest(args: argparse.Namespace) -> int:
    """Walk-forward shadow Final Board vs lvrev over a read-only ``market.db``."""
    import os
    from datetime import date, timedelta

    from ..adoption_gate_cli import _last_bar_date
    from ..backtest_cli import (
        ENV_DB,
        filter_universe,
        load_engine_bars,
        load_engine_industry,
        load_engine_names,
    )
    from ..book_replay import ReplayParams
    from .backtest import (
        compare_shadow_vs_lvrev,
        prepare_shadow_frame,
        render_shadow_backtest_markdown,
    )

    db = (args.db or os.environ.get(ENV_DB, "")).strip()
    if not db or not Path(db).is_file():
        print(f"[fail] market.db 不可用：{db or '未设置 ' + ENV_DB}", file=sys.stderr)
        return 2
    end = (args.end or "").strip() or _last_bar_date(db)
    if not end:
        print("[fail] daily_price 无数据", file=sys.stderr)
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
    payload = compare_shadow_vs_lvrev(
        feats,
        name_map=names,
        params=ReplayParams(
            initial_capital=args.initial_capital, max_positions=args.max_positions
        ),
        top_k=args.top_k,
        index_close=_index_close(db, args.start, end) or None,
        arbitration=args.arbitration,
        min_seats=args.min_seats,
        **_s1_kwargs(args),
    )
    if not payload.get("ok"):
        print(f"[fail] {payload.get('reason')}", file=sys.stderr)
        return 2
    payload["db"] = str(db)
    md = render_shadow_backtest_markdown(payload)
    print(md)
    out_dir = Path(args.bt_out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Factory mode keeps the historical file name; experiment modes get a suffix
    # so a D/A/B comparison never overwrites the factory artefact.
    stem = "shadow_backtest" if args.arbitration == "d" else f"shadow_backtest_{args.arbitration}"
    if args.s1_mode != "pick":
        stem += f"_s1{args.s1_mode}"
        if args.s1_mode == "gate":
            stem += f"_{args.s1_gate_weak}"
        if args.s1_mode == "scale" and args.s1_scale:
            stem += "_" + args.s1_scale.replace(",", "-").replace(".", "p")
    (out_dir / f"{stem}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    print(f"[write] {out_dir}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        prog="stock-platform-shadow-board",
        description=(
            "多策略影子 Final Board（五校 → 硬 Round2 → 仅写 local/shadow/）。"
            "不改出厂 picks / 主绩效；SIMULATE only。"
        ),
    )
    p.add_argument("--asof", default=None, help="锚定日 YYYY-MM-DD（默认今天）")
    p.add_argument(
        "--universe",
        type=Path,
        default=None,
        help="截面宇宙 JSON（list 或 {universe:[]}）；缺省=空宇宙→合法空板",
    )
    p.add_argument("--top-k", type=int, default=8, help="每校 Round1 上限（默认 8）")
    p.add_argument(
        "--shadow-dir",
        type=Path,
        default=None,
        help="影子目录（默认 STOCK_PLATFORM_SHADOW_DIR 或 ./local/shadow）",
    )
    p.add_argument("--no-write", action="store_true", help="只打印，不落盘")
    p.add_argument(
        "--enable-advisory-b",
        action="store_true",
        help="启用集 B 顾问占位（仍不可覆盖硬闸）",
    )
    p.add_argument("--json-out", type=Path, default=None, help="额外写一份 payload JSON")
    p.add_argument("--quiet", action="store_true", help="少打 Markdown 摘要")
    p.add_argument(
        "--perf-summary",
        action="store_true",
        help="只读：打印影子前向绩效账本摘要（A/B 两套指标，不跑终榜）",
    )
    p.add_argument(
        "--settle-daily",
        action="store_true",
        help="结算影子账本 pending 行（引擎 market.db 日线；与主结算同一窗口/alpha 口径），不跑终榜",
    )
    p.add_argument(
        "--backtest",
        action="store_true",
        help="历史 walk-forward 回测：影子终榜 vs lvrev 基线（同一 book_replay 引擎；只读 market.db）",
    )
    p.add_argument("--db", default=None, help="market.db 路径（默认 $STOCK_PLATFORM_ENGINE_MARKET_DB）")
    p.add_argument("--start", default="2024-01-01", help="回测起点 YYYY-MM-DD")
    p.add_argument("--end", default=None, help="回测终点（默认库内最后交易日）")
    p.add_argument("--initial-capital", type=float, default=50000.0)
    p.add_argument("--max-positions", type=int, default=15)
    p.add_argument(
        "--arbitration",
        choices=("d", "a", "b"),
        default="d",
        help=(
            "仅 --backtest：Round2 席位仲裁实验开关。d=出厂（优先级先于分数，默认）；"
            "a=优先级只用于同票去重，按校内分位排序；b=每个非空池学校保底 --min-seats 席。"
            "硬闸三种模式一致；不改出厂默认"
        ),
    )
    p.add_argument(
        "--min-seats",
        type=int,
        default=1,
        help="仅 --arbitration b：每个非空池学校保底席位数（默认 1；空池不保底、不凑满）",
    )
    p.add_argument(
        "--s1-mode",
        choices=("pick", "gate", "scale"),
        default="pick",
        help=(
            "仅 --backtest：S1 大势实验开关。pick=出厂（S1 照常出票，默认）；"
            "gate=S1 不出票，截面宽度弱势/未知日按 --s1-gate-weak 关榜；"
            "scale=S1 不出票，按 regime 缩当日持仓上限。不改出厂默认"
        ),
    )
    p.add_argument(
        "--s1-gate-weak",
        choices=("empty", "s3"),
        default="empty",
        help="仅 --s1-mode gate：弱势日动作。empty=空榜；s3=只放 S3（默认 empty）",
    )
    p.add_argument(
        "--s1-scale",
        default=None,
        help="仅 --s1-mode scale：强,中,弱 三档仓位系数（默认 1,0.5,0；unknown 同弱）",
    )
    p.add_argument(
        "--bt-out-dir",
        type=Path,
        default=Path("local/shadow/backtest"),
        help="回测产物目录（默认 local/shadow/backtest，不提交）",
    )
    args = p.parse_args(argv)

    if args.backtest:
        return _run_backtest(args)

    if args.perf_summary or args.settle_daily:
        from .performance import settle_shadow_ledger, shadow_performance_summary

        shadow_dir = args.shadow_dir or default_shadow_dir()
        if args.settle_daily:
            from ..benchmark import resolve_benchmark_identity, resolve_benchmark_symbol
            from ..performance_cli import _build_settle_get_daily
            from ..symbol_master import name_map_from_master

            get_daily = _build_settle_get_daily()
            bench = resolve_benchmark_symbol()
            identity = resolve_benchmark_identity(
                bench, names=name_map_from_master() or {}
            )
            alpha_ok = bool(identity.get("alphaAvailable", True))
            summary = settle_shadow_ledger(
                shadow_dir=shadow_dir,
                get_daily=get_daily,
                benchmark_get_daily=get_daily if alpha_ok else None,
                benchmark_symbol=bench,
                alpha_available=alpha_ok,
            )
        else:
            summary = shadow_performance_summary(shadow_dir=shadow_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    universe = _load_universe(args.universe)
    payload = run_shadow_board(
        universe,
        asof=args.asof,
        top_k=args.top_k,
        shadow_dir=args.shadow_dir or default_shadow_dir(),
        write=not args.no_write,
        enable_advisory_b=args.enable_advisory_b,
        llm_path=False,
    )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if not args.quiet:
        print(_render_summary(payload))
    print(
        f"shadow-board status={payload.get('status')} "
        f"final={len(payload.get('finalBoard') or [])} "
        f"ledger={payload.get('ledgerPath')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
