"""CLI ``stock-platform-sameday``: 当日战绩（选股 → 次日收盘 · 1 日窗口）。

Examples::

    stock-platform-sameday                      # 最近 5 个归档 asof
    stock-platform-sameday --last 10 --json-out out.json
    stock-platform-sameday --asof 2026-10-12
    stock-platform-sameday --market-db D:/.../market.db
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .dotenv import load_dotenv
from .persistence import open_brief_repository
from .sameday import render_sameday_markdown, summarize_sameday


def _build_get_daily(market_db: str | None):
    """引擎 ``market.db`` 优先；不可用则 fail-closed（绝不静默用 fixtures）。"""
    from stock_platform_providers import EngineSqliteProvider, resolve_engine_market_db

    explicit = str(market_db or "").strip()
    engine_path = Path(explicit) if explicit else resolve_engine_market_db()
    if engine_path is None or not Path(engine_path).is_file():
        return None, None
    provider = EngineSqliteProvider(engine_path)

    def _gd(symbols, *, start, end):
        return list(provider.get_daily(symbols, start=start, end=end) or [])

    return _gd, str(engine_path)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="当日战绩：归档 brief 按 1 日窗口（asof 收盘 → 次日收盘）结算（SIMULATE）"
    )
    p.add_argument("--db", default=None, help="平台 SQLite（默认 STOCK_PLATFORM_DB_URL）")
    p.add_argument("--market-db", default=None, help="引擎 market.db（默认环境变量）")
    p.add_argument("--last", type=int, default=5, help="取最近 N 个归档 asof（默认 5）")
    p.add_argument("--asof", default=None, help="只统计该 asof（YYYY-MM-DD）")
    p.add_argument("--holding", default="1d", help="持有窗口（默认 1d = 当日战绩）")
    p.add_argument("--benchmark", default="000905", help="基准代码（默认中证500 000905）")
    p.add_argument("--json-out", type=Path, help="聚合 payload 写入 JSON")
    p.add_argument("--out", type=Path, help="markdown 写入文件")
    args = p.parse_args(argv)

    repo = open_brief_repository(args.db)
    if args.asof:
        record = repo.get_by_asof(str(args.asof)[:10])
        records = [record.to_dict()] if record is not None else []
    else:
        records = [r.to_dict() for r in repo.list_recent(limit=max(int(args.last), 1))]
    records = sorted(records, key=lambda r: str(r.get("asof") or ""))

    get_daily, engine = _build_get_daily(args.market_db)
    payload: dict[str, Any] = {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "engineMarketDb": engine,
        "archivedBriefs": [str(r.get("asof") or "") for r in records],
        "failClosed": get_daily is None,
    }
    if get_daily is None:
        payload["error"] = (
            "无可用日线源：请配置 STOCK_PLATFORM_ENGINE_MARKET_DB 指向 "
            "a-stock-engine/data_cache/market.db（只读），或用 --market-db 指定。"
        )
        md = (
            "# 当日战绩（选股 → 次日收盘）\n\n"
            f"**fail-closed：{payload['error']}**\n"
        )
    else:
        if not records:
            payload["error"] = "归档 brief 为空：无 asof 可结算"
            md = "# 当日战绩（选股 → 次日收盘）\n\n**归档 brief 为空，无可结算的 asof。**\n"
        else:
            summary = summarize_sameday(
                records,
                get_daily=get_daily,
                benchmark_get_daily=get_daily,
                benchmark_symbol=args.benchmark,
                holding=args.holding,
            )
            payload["summary"] = summary
            md = render_sameday_markdown(summary)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")

    print(md)
    summary = payload.get("summary") or {}
    print(
        "sameday holding={h} settled={s} pending={p} avg={a} bench={b}".format(
            h=summary.get("holding"),
            s=summary.get("settledCount"),
            p=summary.get("pendingCount"),
            a=summary.get("avgRawReturn"),
            b=summary.get("benchmarkSymbol"),
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
