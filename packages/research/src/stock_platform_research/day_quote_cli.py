"""CLI ``stock-platform-day-quote``: 盘后当日行情台账（开/高/低/收 + 涨跌 + 量化归因）。

Examples::

    stock-platform-day-quote --asof 2026-10-22
    stock-platform-day-quote --asof 2026-10-22 --no-ohlc      # 完全离线，只用引擎库
    stock-platform-day-quote --last-brief --json-out out.json

数据来源分工（有意为之）：

* **收盘/成交量/均线** ← 引擎 ``market.db``（与主链同一份当日截面，口径不会漂）
* **开盘/最高/最低** ← 外部日线（引擎 ``daily_price`` 无这三列），落缓存
  ``data/quotes/ohlc-<asof>.json`` 保证**同日复跑零网络且结果一致**；
  取不到就降级为 ``—``，绝不补零。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .day_quote import (
    OHLC_CACHE,
    OHLC_MISSING,
    OHLC_PROVIDER,
    build_day_quote,
    render_day_quote_markdown,
)
from .dotenv import load_dotenv
from .persistence import open_brief_repository
from .symbol_master import name_map_from_master

_REPO = Path(__file__).resolve().parents[4]
DEFAULT_HOLDINGS = _REPO / "data" / "holdings.json"
DEFAULT_CACHE_DIR = _REPO / "data" / "quotes"
LOOKBACK_DAYS = 120  # 覆盖 MA20 + 20 日均量 + 停牌缓冲


def _engine_provider(market_db: str | None):
    """引擎 ``market.db``（只读）。不可用返回 ``(None, None)``，由调用方 fail-closed。"""
    from stock_platform_providers import EngineSqliteProvider, resolve_engine_market_db

    explicit = str(market_db or "").strip()
    path = Path(explicit) if explicit else resolve_engine_market_db()
    if path is None or not Path(path).is_file():
        return None, None
    return EngineSqliteProvider(path), str(path)


def _load_holdings(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("holdings") or []
    return [dict(r) for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _code_of(row: dict[str, Any]) -> str:
    for key in ("code", "symbol", "ts_code"):
        if row.get(key):
            return str(row[key]).strip()
    return ""


def _cache_path(cache_dir: Path, asof: str) -> Path:
    return cache_dir / f"ohlc-{asof}.json"


def _read_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 坏缓存视作无缓存
        return {}
    rows = blob.get("rows") or {}
    return {str(k): dict(v) for k, v in rows.items() if isinstance(v, dict)}


CHUNK_SIZE = 30
CHUNK_ATTEMPTS = 2
CHUNK_PAUSE_SEC = 0.8
FETCH_PASSES = 3  # get_daily 对单只瞬时错误是静默跳过，需逐轮补齐
FETCH_PASSES = 3  # get_daily 对单只瞬时错误是静默跳过，需逐轮补齐


def _fetch_ohlc_chunk(symbols: list[str], start: date, end: date) -> list[dict[str, Any]]:
    """One chunk through a **fresh** provider (fresh circuit breaker)."""
    from stock_platform_providers.astock_http import AStockHttpProvider

    return list(AStockHttpProvider().get_daily(symbols, start=start, end=end) or [])


def _fetch_ohlc(symbols: list[str], asof: str) -> tuple[dict[str, dict[str, Any]], str | None]:
    """外部日线补开/高/低。返回 ``(rows, error)``；任何异常都只降级、不抛出。

    两层韧性 —— 2026-10-29 盘后实测：东财 ``RemoteDisconnected`` → 断路器打开 →
    70+ 只**整批全灭** → 简报「开盘/收盘/涨跌」三列全空。

    1. **分批**（``CHUNK_SIZE``）：``AStockHttpProvider.get_daily`` 碰上断路器是整体
       抛出，一次调用全部符号会把已拿到的数据一起丢掉。分批后单批失败只损失该批，
       并换一个新建 provider（断路器是实例级的）重试一次。
    2. **逐轮补齐**（``FETCH_PASSES``）：``get_daily`` 对**单只**的瞬时错误是
       **静默跳过**（只塞进 ``symbol_errors``，不抛异常），所以一次调用常常「调用成功
       但少回几只」。对仍然缺的代码再跑下一轮，直到补齐或轮次用尽。
    """
    day = date.fromisoformat(str(asof)[:10])
    start = day - timedelta(days=10)
    by_symbol: dict[str, dict[str, Any]] = {}
    pending = [s for s in dict.fromkeys(str(s) for s in symbols) if s]
    total = len(pending)
    last_err: str | None = None
    for pass_no in range(1, FETCH_PASSES + 1):
        if not pending:
            break
        for offset in range(0, len(pending), CHUNK_SIZE):
            chunk = pending[offset : offset + CHUNK_SIZE]
            bars: list[dict[str, Any]] | None = None
            for attempt in range(1, CHUNK_ATTEMPTS + 1):
                try:
                    bars = _fetch_ohlc_chunk(chunk, start, day)
                    break
                except Exception as exc:  # noqa: BLE001 — 单批失败只降级
                    last_err = f"{type(exc).__name__}: {exc}"[:200]
                    bars = None
                    if attempt < CHUNK_ATTEMPTS:
                        time.sleep(CHUNK_PAUSE_SEC * attempt)
            if bars is None:
                continue
            for bar in bars:
                sym = str(bar.get("symbol") or "").split(".")[0].zfill(6)
                if str(bar.get("date") or "")[:10] != day.isoformat():
                    continue
                by_symbol[sym] = {
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                }
        pending = [
            s for s in pending if s.split(".")[0].zfill(6) not in by_symbol
        ]
        if pending and pass_no < FETCH_PASSES:
            time.sleep(CHUNK_PAUSE_SEC * pass_no)
    if not by_symbol:
        return {}, f"全部失败（{last_err or '无数据返回'}）"[:300]
    if pending:
        return by_symbol, (
            f"部分缺失（缺 {len(pending)}/{total} 只；最后错误 {last_err}）"[:300]
        )
    return by_symbol, None


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="盘后当日行情台账：开/高/低/收 + 涨跌 + 量化归因（SIMULATE）"
    )
    p.add_argument("--asof", default=None, help="数据基准日 YYYY-MM-DD（默认取最新归档 brief）")
    p.add_argument("--db", default=None, help="平台 SQLite（默认 STOCK_PLATFORM_DB_URL）")
    p.add_argument("--market-db", default=None, help="引擎 market.db（默认环境变量）")
    p.add_argument("--holdings", default=str(DEFAULT_HOLDINGS), help="持仓账本 JSON")
    p.add_argument("--benchmark", default="000905", help="基准代码（默认中证500 000905）")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="OHLC 缓存目录")
    p.add_argument("--no-ohlc", action="store_true", help="完全不联网，只用引擎库（无开盘价）")
    p.add_argument("--json-out", type=Path, help="payload 写入 JSON")
    p.add_argument("--out", type=Path, help="markdown 写入文件")
    args = p.parse_args(argv)

    repo = open_brief_repository(args.db)
    asof = str(args.asof or "").strip()[:10]
    record = repo.get_by_asof(asof) if asof else None
    if record is None and not asof:
        recent = repo.list_recent(limit=1)
        if recent:
            record = recent[0]
            asof = str(record.asof)[:10]
    if not asof:
        print("# 当日行情台账\n\n**fail-closed：无归档 brief，无法确定 asof。**\n")
        return 2

    provider, engine_path = _engine_provider(args.market_db)
    if provider is None:
        md = "# 当日行情台账\n\n**fail-closed：无可用引擎 market.db（只读）。**\n"
        print(md)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(md, encoding="utf-8")
        return 2

    names = name_map_from_master() or {}
    targets: list[dict[str, Any]] = []
    if record is not None:
        for pick in record.picks or []:
            sym = str(pick.get("symbol") or "").strip()
            if sym:
                targets.append({"symbol": sym, "name": names.get(sym) or "—", "bucket": "pick"})
    for row in _load_holdings(Path(args.holdings)):
        sym = _code_of(row)
        if sym:
            targets.append(
                {
                    "symbol": sym,
                    "name": str(row.get("name") or names.get(sym) or "—"),
                    "bucket": "holding",
                }
            )

    symbols = sorted({t["symbol"] for t in targets})
    fetch_symbols = sorted(set(symbols) | {args.benchmark})
    start = date.fromisoformat(asof) - timedelta(days=LOOKBACK_DAYS)
    end = date.fromisoformat(asof)
    bars = list(provider.get_daily(fetch_symbols, start=start, end=end) or [])
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for bar in bars:
        sym = str(bar.get("symbol") or "").split(".")[0].zfill(6)
        bars_by_symbol.setdefault(sym, []).append(bar)

    cache_dir = Path(args.cache_dir)
    cache_file = _cache_path(cache_dir, asof)
    ohlc: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    status: dict[str, Any] = {"requested": len(fetch_symbols), "source": "none", "degraded": None}
    if not args.no_ohlc:
        cached = _read_cache(cache_file)
        if cached:
            ohlc.update(cached)
            sources.update({k: OHLC_CACHE for k in cached})
            status["source"] = "cache"
        missing = [s for s in fetch_symbols if s not in ohlc]
        if missing:
            fetched, err = _fetch_ohlc(missing, asof)
            if fetched:
                ohlc.update(fetched)
                sources.update({k: OHLC_PROVIDER for k in fetched})
                status["source"] = "cache+provider" if cached else "provider"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps(
                        {"asof": asof, "rows": ohlc, "count": len(ohlc)},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            if err:
                status["degraded"] = f"外部日线源不可用（{err}）"
        if len(ohlc) < len(fetch_symbols):
            gaps = [s for s in fetch_symbols if s not in ohlc]
            status["missing"] = gaps
    else:
        status["degraded"] = "--no-ohlc：未取开盘价（离线模式）"
    status["filled"] = sum(1 for s in fetch_symbols if s in ohlc)

    bench_name = names.get(str(args.benchmark).split(".")[0].zfill(6)) or None
    bench_warning = None
    if bench_name:
        bench_warning = (
            f"平台基准 `{args.benchmark}` 在引擎库中解析为 **{bench_name}**（个股），"
            "并非中证500 指数点位；因此「相对基准」列是相对该**个股**的超额，"
            "**不能读作指数超额**（A4 绩效台账的 avgAlpha 用的是同一口径）。"
        )

    payload = build_day_quote(
        targets,
        asof=asof,
        bars_by_symbol=bars_by_symbol,
        benchmark_symbol=args.benchmark,
        benchmark_bars=bars_by_symbol.get(args.benchmark) or [],
        ohlc_by_symbol=ohlc,
        ohlc_sources=sources,
        ohlc_status=status,
        benchmark_name=bench_name,
        benchmark_warning=bench_warning,
    )
    payload["engineMarketDb"] = engine_path
    payload["briefAsof"] = str(record.asof)[:10] if record is not None else None
    payload["pickCount"] = sum(1 for t in targets if t["bucket"] == "pick")
    payload["holdingCount"] = sum(1 for t in targets if t["bucket"] == "holding")
    payload["ohlcCache"] = str(cache_file)

    md = render_day_quote_markdown(payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")

    print(md)
    summary = payload.get("summary") or {}
    print(
        "day_quote asof={a} up={u} down={d} avg={m} ohlc={f}/{r}".format(
            a=asof,
            u=summary.get("upCount"),
            d=summary.get("downCount"),
            m=summary.get("avgPct"),
            f=status.get("filled"),
            r=status.get("requested"),
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
