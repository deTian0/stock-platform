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

# CN minute bars — datetime is Beijing wall-clock naive (no tz / no UTC storage).
MINUTE_COLUMNS = [
    "symbol",
    "asset_type",
    "source",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "freq",
]

MINUTE_FREQS = frozenset({"1m", "5m", "15m", "30m", "60m"})

# CN day-level fund flow (元). Platform extension beyond TSP original seven.
FUND_FLOW_COLUMNS = [
    "symbol",
    "asset_type",
    "source",
    "date",
    "main_net",
    "small_net",
    "mid_net",
    "large_net",
    "super_net",
]

# CN dragon-tiger board (龙虎榜) aggregate payload keys (amounts in 元).
LHB_TOP_KEYS = [
    "symbol",
    "asset_type",
    "source",
    "asof_date",
    "look_back_days",
    "records",
    "seats",
    "institution",
]

LHB_RECORD_COLUMNS = [
    "date",
    "reason",
    "net_buy",
    "turnover_rate",
]

LHB_SEAT_COLUMNS = [
    "name",
    "buy_amt",
    "sell_amt",
    "net",
]

LHB_INSTITUTION_COLUMNS = [
    "buy_amt",
    "sell_amt",
    "net_amt",
]

# CN lockup / unlock calendar (限售解禁) aggregate payload (shares in 万股).
UNLOCK_TOP_KEYS = [
    "symbol",
    "asset_type",
    "source",
    "asof_date",
    "forward_days",
    "history",
    "upcoming",
]

UNLOCK_EVENT_COLUMNS = [
    "date",
    "type",
    "shares",
    "able_shares",
    "ratio",
]
