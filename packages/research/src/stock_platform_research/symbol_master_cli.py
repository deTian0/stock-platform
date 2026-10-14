"""CLI ``stock-platform-symbol-master``: 维护本地「代码 ↔ 名称」主数据表。

Examples::

    stock-platform-symbol-master --refresh            # 从引擎 market.db 全量刷新
    stock-platform-symbol-master --stats              # 覆盖率体检（按数据源）
    stock-platform-symbol-master --lookup 601038,000801
    stock-platform-symbol-master --list --limit 20    # 抽样查看映射表
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .dotenv import load_dotenv
from .symbol_master import (
    ENV_ENGINE_MARKET_DB,
    open_symbol_master,
    refresh_from_engine,
    resolve_engine_market_db,
)


def main(argv: list[str] | None = None) -> int:
    # Load repo-root .env so CLI == .bat behaviour (P0-2).
    load_dotenv()
    p = argparse.ArgumentParser(
        description="Local symbol master: 代码 ↔ 名称 映射表（全量、幂等刷新）"
    )
    p.add_argument(
        "--db",
        default=None,
        help="SQLite path/URL (default STOCK_PLATFORM_DB_URL or ./data/stock_platform.db)",
    )
    p.add_argument(
        "--market-db",
        default=None,
        help=f"引擎 market.db 路径（默认 ${ENV_ENGINE_MARKET_DB}）",
    )
    p.add_argument("--refresh", action="store_true", help="从引擎 fundamentals 全量刷新")
    p.add_argument("--stats", action="store_true", help="覆盖率体检（按数据源分组）")
    p.add_argument("--lookup", default=None, help="逗号分隔的代码，查名称")
    p.add_argument("--list", action="store_true", help="导出映射表（配合 --limit）")
    p.add_argument("--limit", type=int, default=20, help="--list 行数上限（默认 20）")
    p.add_argument("--json-out", type=Path, help="结构化结果写入 JSON")
    args = p.parse_args(argv)

    repo = open_symbol_master(args.db)
    out: dict[str, Any] = {
        "dbPath": str(getattr(repo, "_path", args.db)),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "engineMarketDb": str(resolve_engine_market_db(args.market_db) or ""),
        "count": repo.count(),
    }
    did_something = False

    if args.refresh:
        refreshed = refresh_from_engine(args.market_db, db_url=args.db)
        out["refresh"] = refreshed
        out["count"] = refreshed["total"]
        did_something = True

    if args.lookup:
        codes = [c.strip() for c in str(args.lookup).split(",") if c.strip()]
        out["lookup"] = repo.resolve_many(codes)
        out["missing"] = [c for c in codes if c not in out["lookup"]]
        did_something = True

    if args.list:
        table = repo.load()
        items = sorted(table.items())[: max(int(args.limit), 1)]
        out["items"] = [{"code": c, "name": n} for c, n in items]
        did_something = True

    if args.stats or not did_something:
        out["stats"] = repo.stats()

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    if "refresh" in out:
        r = out["refresh"]
        print(
            f"symbol_master refresh ok={r['ok']} written={r['written']} total={r['total']}"
            + (f" reason={r['reason']}" if r.get("reason") else ""),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
