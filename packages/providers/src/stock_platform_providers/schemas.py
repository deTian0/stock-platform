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

# CN adjustment / ex-rights factors (复权因子). Column name is ex_factor (not adj_factor).
ADJ_FACTOR_COLUMNS = [
    "symbol",
    "asset_type",
    "source",
    "trade_date",
    "ex_factor",
]

ADJ_FACTOR_KINDS = frozenset({"qfq", "hfq"})

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

# full_minute reuses MINUTE_COLUMNS with freq fixed to 1m (same-day batch / repair).
FULL_MINUTE_FREQ = "1m"
FULL_MINUTE_DEFAULT_COUNT = 300

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

# CN board / sector day-level fund flow (元). M41 / Phase E.
SECTOR_FUND_FLOW_COLUMNS = [
    "sector_code",
    "sector_name",
    "asset_type",
    "source",
    "date",
    "main_net",
    "change_pct",
]

# Lightweight news features (not LLM summaries). M41 / Phase E.
NEWS_COLUMNS = [
    "symbol",
    "sector_code",
    "date",
    "title",
    "summary",
    "source",
    "sentiment",
]

# CN concept / industry / region board membership (个股所属板块). M-D3 / ADR 0051.
CONCEPT_BLOCKS_TOP_KEYS = [
    "symbol",
    "asset_type",
    "source",
    "total",
    "boards",
    "concept_tags",
]

CONCEPT_BLOCK_COLUMNS = [
    "name",
    "code",
    "change_pct",
    "lead_stock",
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

# CN five-level order book (五档盘口). Volumes in 手; prices in 元.
DEPTH5_COLUMNS = [
    "symbol",
    "asset_type",
    "source",
    "bid_prices",
    "bid_volumes",
    "ask_prices",
    "ask_volumes",
    "asof_ts",
]

DEPTH5_LEVELS = 5

# CN financial statements aggregate (三表). Amounts in 元.
FINANCIAL_TOP_KEYS = [
    "symbol",
    "asset_type",
    "source",
    "periods",
    "income",
    "balance",
    "cashflow",
]

FINANCIAL_INCOME_COLUMNS = [
    "period_end",
    "revenue",
    "net_income",
    "net_income_attributable",
    "basic_eps",
]

FINANCIAL_BALANCE_COLUMNS = [
    "period_end",
    "total_assets",
    "total_liabilities",
    "total_equity",
]

FINANCIAL_CASHFLOW_COLUMNS = [
    "period_end",
    "net_operating_cash_flow",
    "net_investing_cash_flow",
    "net_financing_cash_flow",
]
