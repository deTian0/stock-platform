"""CLI: summarize recommend decision performance from JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .performance import (
    align_fills_to_performance,
    default_performance_log_path,
    load_jsonl,
    performance_summary,
    rewrite_jsonl,
    settle_pending_entries,
    settle_performance_log,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Summarize settled recommend decisions (holding-period metrics)."
    )
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="JSONL path (default STOCK_PLATFORM_PERFORMANCE_LOG or ./data/recommend_decisions.jsonl)",
    )
    p.add_argument(
        "--settle-fixture",
        type=Path,
        help="Optional JSON map {(date|symbol): raw_return_float} to settle pending rows",
    )
    p.add_argument(
        "--settle-daily",
        action="store_true",
        help=(
            "Settle pending via daily provider: prefer STOCK_PLATFORM_ENGINE_MARKET_DB "
            "(engine_sqlite), else STOCK_PLATFORM_PROVIDER_PRESET daily"
        ),
    )
    p.add_argument(
        "--align-fills",
        type=Path,
        help="Optional JSON array of fill-like dicts (symbol/side/qty/price/ts) → append pending rows",
    )
    p.add_argument(
        "--holding",
        default="5d",
        help="Holding tag for --align-fills pending rows (default 5d)",
    )
    p.add_argument("--json-out", type=Path, help="Write summary JSON")
    args = p.parse_args(argv)

    log_path = args.log or default_performance_log_path()
    if args.align_fills and args.align_fills.is_file():
        fills = json.loads(args.align_fills.read_text(encoding="utf-8"))
        if not isinstance(fills, list):
            raise SystemExit("--align-fills must be a JSON array of fill-like objects")
        align_fills_to_performance(fills, holding=args.holding, log_path=log_path)

    entries = load_jsonl(log_path)
    summary = None
    if args.settle_fixture and args.settle_fixture.is_file():
        raw_map = json.loads(args.settle_fixture.read_text(encoding="utf-8"))
        returns = {}
        for k, v in raw_map.items():
            if "|" in k:
                d, s = k.split("|", 1)
                returns[(d, s)] = float(v)
        entries = settle_pending_entries(entries, returns=returns)
        rewrite_jsonl(log_path, entries)
    elif args.settle_daily:
        get_daily = _build_settle_get_daily()
        summary = settle_performance_log(log_path, get_daily=get_daily)
        entries = load_jsonl(log_path)

    if summary is None:
        summary = performance_summary(log_path, entries=entries)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    m = summary["metrics"]
    print(
        f"settled={summary['settledCount']} "
        f"direction_accuracy={m.get('direction_accuracy')} "
        f"avg_return={m.get('avg_return')} "
        f"settledNewly={summary.get('settledNewly', 0)}"
    )
    return 0


def _build_settle_get_daily():
    """Resolve get_daily for CLI settle: engine_sqlite first, else preset daily."""
    from stock_platform_providers import (
        EngineSqliteProvider,
        ReplayProvider,
        ReplayTransport,
        resolve_engine_market_db,
        startup_preferences,
    )

    engine_path = resolve_engine_market_db()
    if engine_path is not None:
        provider = EngineSqliteProvider(engine_path)

        def _gd(symbols, *, start, end):
            return list(provider.get_daily(symbols, start=start, end=end) or [])

        return _gd

    prefs = startup_preferences()
    daily_name = prefs.get("daily", "replay")
    if daily_name == "replay":
        # Prefer packaged workbench/providers fixtures when present.
        here = Path(__file__).resolve()
        candidates = [
            here.parents[4] / "apps" / "workbench" / "tests" / "fixtures",
            here.parents[3] / "providers" / "tests" / "fixtures",
        ]
        fixtures = next((p for p in candidates if p.is_dir()), None)
        if fixtures is None:
            raise SystemExit("--settle-daily: no engine db and no replay fixtures found")
        provider = ReplayProvider(ReplayTransport(fixtures))

        def _gd_replay(symbols, *, start, end):
            return list(provider.get_daily(symbols, start=start, end=end) or [])

        return _gd_replay

    if daily_name == "tushare_http":
        from stock_platform_providers import TushareHttpProvider

        provider = TushareHttpProvider()

        def _gd_ts(symbols, *, start, end):
            return list(provider.get_daily(symbols, start=start, end=end) or [])

        return _gd_ts

    if daily_name == "astock_http":
        from stock_platform_providers import AStockHttpProvider

        provider = AStockHttpProvider()

        def _gd_em(symbols, *, start, end):
            return list(provider.get_daily(symbols, start=start, end=end) or [])

        return _gd_em

    if daily_name == "engine_sqlite":
        raise SystemExit(
            "--settle-daily: STOCK_PLATFORM_ENGINE_MARKET_DB missing for engine_sqlite"
        )

    raise SystemExit(f"--settle-daily: unsupported daily provider {daily_name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
