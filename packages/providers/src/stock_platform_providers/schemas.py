"""Internal schema column lists — aligned with docs/contracts/datasets.md."""

from __future__ import annotations

DAILY_COLUMNS = [
    "symbol",
    "asset_type",
    "source",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pre_close",
    "change_pct",
    "quote_ts",
]

REALTIME_COLUMNS = [
    "symbol",
    "name",
    "price",
    "prev_close",
    "change_amount",
    "change_pct",
    "amplitude",
    "turnover_rate",
    "volume",
    "amount",
    "asof_ts",
    "source",
    "asset_type",
]
