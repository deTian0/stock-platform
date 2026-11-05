"""CLI ``stock-platform-debate`` — advisory debate lane (never writes picks/绩效)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


def _provider(name: str, market_db: str | None):
    from stock_platform_providers import EngineSqliteProvider, resolve_engine_market_db

    if name in {"engine", "workbuddy", "replay"}:
        path = Path(market_db) if market_db else resolve_engine_market_db()
        if path is None or not Path(path).is_file():
            raise SystemExit(
                "需要可读引擎 market.db：设 STOCK_PLATFORM_ENGINE_MARKET_DB 或 --market-db"
            )
        return EngineSqliteProvider(path)
    # Default: same engine path (HTTP providers need keys; agent day-use is RO warehouse).
    path = Path(market_db) if market_db else resolve_engine_market_db()
    if path is None or not Path(path).is_file():
        raise SystemExit("需要可读引擎 market.db")
    return EngineSqliteProvider(path)


def _brief_from_symbols(symbols: list[str], asof: str) -> dict[str, Any]:
    picks = [
        {"symbol": s, "rank": i + 1, "name": s}
        for i, s in enumerate(symbols)
        if str(s).strip()
    ]
    return {
        "asof": asof,
        "picks": picks,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "provider": "debate-cli",
    }


def _load_brief(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("--from-brief 须为 JSON 对象")
    return data


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="stock-platform-debate",
        description="顾问辩论侧车（excludedFromPerformance；默认 SIMULATE）。",
    )
    p.add_argument(
        "--engine",
        choices=("off", "deterministic", "llm"),
        default="deterministic",
        help="辩论引擎（llm 需 STOCK_PLATFORM_LLM_DEBATE=1 + 提供商配置）",
    )
    p.add_argument("--symbol", action="append", default=[], help="可重复；组成临时 brief")
    p.add_argument("--from-brief", type=Path, default=None, help="归档/导出 brief JSON")
    p.add_argument("--asof", default=None, help="YYYY-MM-DD（默认今天）")
    p.add_argument("--max-picks", type=int, default=None)
    p.add_argument(
        "--provider",
        default="engine",
        help="行情源标签（当前实现：engine/workbuddy → 只读 market.db）",
    )
    p.add_argument("--market-db", default=None)
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--summary", action="store_true", help="只输出 summary（无 round 正文）")
    args = p.parse_args(argv)

    asof = str(args.asof or date.today().isoformat())[:10]
    if args.from_brief:
        brief = _load_brief(args.from_brief)
        if not brief.get("asof"):
            brief["asof"] = asof
    elif args.symbol:
        brief = _brief_from_symbols([str(s).strip() for s in args.symbol], asof)
    else:
        p.error("需要 --symbol 或 --from-brief")

    from .debate_lane import attach_debate_lane, debate_lane_summary

    provider = _provider(str(args.provider), args.market_db)
    lane = attach_debate_lane(
        provider,
        brief,
        engine=args.engine,
        max_picks=args.max_picks,
    )
    out: dict[str, Any] = debate_lane_summary(lane) if args.summary else lane
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    print(
        f"debate engine={lane.get('engine')} count={lane.get('debateCount')} "
        f"excludedFromPerformance={lane.get('excludedFromPerformance')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
