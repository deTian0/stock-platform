"""Initialize platform runtime config in the local SQLite DB.

Idempotent: missing singleton row → seed required fields; existing row → print
status unless ``--force``. Never opens live trading.

Examples::

    stock-platform-init
    stock-platform-init --db-url sqlite:///./local/stock_platform.db
    stock-platform-init --force --broker 华宝证券 --capital-limit 10000
"""

from __future__ import annotations

import argparse
import json
import sys

from .runtime_config import (
    DEFAULT_BROKER_SUGGESTION,
    DEFAULT_CAPITAL_LIMIT_CNY,
    DEFAULT_HOLDINGS_PATH,
    seed_runtime_config,
)
from .settings import get_settings


def main(argv: list[str] | None = None) -> int:
    get_settings()
    parser = argparse.ArgumentParser(
        prog="stock-platform-init",
        description=(
            "Seed platform_runtime_config in stock_platform.db when missing. "
            "Idempotent; never enables live trading."
        ),
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLite URL/path (default STOCK_PLATFORM_DB_URL or ./local/stock_platform.db)",
    )
    parser.add_argument(
        "--broker",
        default=DEFAULT_BROKER_SUGGESTION,
        help=f"Broker suggestion text (default {DEFAULT_BROKER_SUGGESTION!r})",
    )
    parser.add_argument(
        "--capital-limit",
        type=float,
        default=DEFAULT_CAPITAL_LIMIT_CNY,
        help=f"Nominal capital limit CNY (default {DEFAULT_CAPITAL_LIMIT_CNY})",
    )
    parser.add_argument(
        "--holdings-path",
        default=DEFAULT_HOLDINGS_PATH,
        help=f"Default holdings JSON path (default {DEFAULT_HOLDINGS_PATH})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing config row (live_trading_enabled stays 0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the resulting config as JSON",
    )
    args = parser.parse_args(argv)

    try:
        config, created = seed_runtime_config(
            args.db_url,
            broker_suggestion=args.broker,
            capital_limit_cny=args.capital_limit,
            holdings_path=args.holdings_path,
            force=args.force,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[ERROR] database unavailable: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = config.to_dict()
        payload["created"] = created
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "created" if created else ("updated" if args.force else "exists")
        print(f"platform_runtime_config: {action}")
        print(f"  brokerSuggestion   = {config.broker_suggestion}")
        print(f"  capitalLimitCny    = {config.capital_limit_cny}")
        print(f"  holdingsPath       = {config.holdings_path}")
        print(f"  liveTradingEnabled = {config.live_trading_enabled} (always false)")
        print(f"  updatedAt          = {config.updated_at}")
        if not created and not args.force:
            print("  (pass --force to overwrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
