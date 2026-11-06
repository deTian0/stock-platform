"""CLI ``stock-platform-aux-market`` — platform-owned supplement market store (ADR 0095).

Pulls verified index daily bars (+ optional explicit stock OHLC) through ``em_get``
into ``local/aux_market/aux_market.db`` (``STOCK_PLATFORM_AUX_MARKET_DB``).
Never writes the engine ``market.db``. Exit code 0 unless arguments are invalid
(fail-soft: per-code failures are reported, not raised).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .dotenv import load_dotenv


def _split(text: str | None) -> list[str]:
    return [x.strip() for x in str(text or "").split(",") if x.strip()]


def _date(text: str) -> date:
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError as exc:
        raise SystemExit(f"日期格式需 YYYY-MM-DD：{text!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    from stock_platform_providers.aux_market import DEFAULT_INDICES, ENV_AUX_MARKET_DB, ENV_AUX_MARKET_EM_BUDGET

    p = argparse.ArgumentParser(
        prog="stock-platform-aux-market",
        description="平台自有补充行情库（指数日线 + 指定个股 OHLC，经 em_get；不写 market.db）",
    )
    p.add_argument(
        "--indices",
        default=None,
        help=f"逗号列表；默认 {','.join(DEFAULT_INDICES)}；传空串 '' 不抓指数",
    )
    p.add_argument("--codes", default="", help="个股代码逗号列表（默认不抓个股，不做全市场）")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default=None, help="默认今天（Asia/Shanghai）")
    p.add_argument("--db", default=None, help=f"补充库路径（默认 ${ENV_AUX_MARKET_DB} 或 local/aux_market/aux_market.db）")
    p.add_argument("--budget", type=int, default=None, help=f"当日请求预算（默认 ${ENV_AUX_MARKET_EM_BUDGET} 或 60）")
    p.add_argument("--dry-run", action="store_true", help="只打印计划：零网络、不建库")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    from stock_platform_providers.aux_market import (
        DEFAULT_INDICES,
        plan_aux_sync,
        resolve_aux_market_db,
        sync_aux_market,
    )

    from .benchmark import aux_index_name_hints

    args = build_parser().parse_args(argv)
    indices = list(DEFAULT_INDICES) if args.indices is None else _split(args.indices)
    codes = _split(args.codes)
    start = _date(args.start)
    end = _date(args.end) if args.end else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if end < start:
        print(f"[fail] --end {end} 早于 --start {start}", file=sys.stderr)
        return 2
    if not indices and not codes:
        print("[fail] 未指定 --indices / --codes", file=sys.stderr)
        return 2

    db = resolve_aux_market_db(args.db)
    if args.dry_run:
        plan = plan_aux_sync(indices=indices, codes=codes, start=start, end=end)
        out: dict[str, Any] = {"dryRun": True, "db": str(db), "requests": len(plan), "plan": plan}
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"[dry-run] db={db} 请求数={len(plan)}（零网络、未建库）")
            for row in plan:
                flag = "" if row.get("supported") else f"  ✗ {row.get('reason') or '不支持'}"
                print(f"  {row['kind']:<5} {row['code']:<10} secid={row.get('secid')} {row['start']}~{row['end']}{flag}")
        return 0

    res = sync_aux_market(
        indices=indices,
        codes=codes,
        start=start,
        end=end,
        name_hints=aux_index_name_hints(),
        db_path=db,
        daily_budget=args.budget,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"[aux] db={res.get('db')} ok={res.get('ok')} budget={res.get('budget')}")
        if res.get("error"):
            print(f"[aux] error: {res['error']}")
        for r in res.get("results") or []:
            span = f" {r.get('first')}~{r.get('last')}" if r.get("first") else ""
            name = f" name={r.get('name')}" if r.get("name") else ""
            reason = f" reason={r.get('reason')}" if r.get("reason") else ""
            print(f"  {r['kind']:<5} {r['code']:<10} {r['status']:<15} rows={r.get('rows')}{span}{name}{reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
