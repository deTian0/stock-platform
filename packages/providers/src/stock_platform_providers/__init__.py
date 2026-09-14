"""stock-platform providers â€?unified Vendor surface (A-share first, US/HK via market)."""

from .adjust import apply_adjust
from .astock_http import AStockHttpProvider, em_board_secid, em_secid
from .calendar import TradingCalendar, get_trading_calendar
from .capabilities import (
    CAPABILITY_IDS,
    CAPABILITY_REGISTRY,
    ProviderDeclaration,
    build_capability_matrix,
    get_provider_registry,
    register_builtin_providers,
    reset_provider_registry,
)
from .eastmoney import (
    CircuitOpenError,
    EastmoneyClient,
    em_get,
    http_trust_env,
    is_eastmoney_url,
    reset_default_client,
)
from .presets import (
    DEFAULT_STARTUP_PRESET,
    ENV_PROVIDER_PRESET,
    PREFERENCE_PRESETS,
    get_preference_preset,
    list_preference_presets,
    resolve_startup_preset_id,
    startup_preferences,
)
from .errors import SymbolError
from .global_http import GlobalHttpProvider, GlobalHttpRouter, infer_global_market
from .global_replay import GlobalReplayProvider, GlobalReplayTransport
from .market import (
    LimitRule,
    MarketStrategy,
    SettleRule,
    SessionSegment,
    SymbolRef,
    get_market_strategy,
    list_market_ids,
)
from .replay import ReplayProvider, ReplayTransport
from .symbol import (
    exchange_prefix,
    is_bse_symbol,
    normalize_sector_code,
    normalize_symbol,
)

__all__ = [
    "AStockHttpProvider",
    "apply_adjust",
    "CAPABILITY_IDS",
    "CAPABILITY_REGISTRY",
    "CircuitOpenError",
    "EastmoneyClient",
    "GlobalHttpProvider",
    "GlobalHttpRouter",
    "GlobalReplayProvider",
    "GlobalReplayTransport",
    "LimitRule",
    "MarketStrategy",
    "ProviderDeclaration",
    "ReplayProvider",
    "ReplayTransport",
    "SettleRule",
    "SessionSegment",
    "SymbolError",
    "SymbolRef",
    "TradingCalendar",
    "build_capability_matrix",
    "em_board_secid",
    "em_get",
    "em_secid",
    "http_trust_env",
    "DEFAULT_STARTUP_PRESET",
    "ENV_PROVIDER_PRESET",
    "get_preference_preset",
    "list_preference_presets",
    "PREFERENCE_PRESETS",
    "resolve_startup_preset_id",
    "startup_preferences",
    "exchange_prefix",
    "get_market_strategy",
    "get_provider_registry",
    "get_trading_calendar",
    "infer_global_market",
    "is_bse_symbol",
    "is_eastmoney_url",
    "list_market_ids",
    "normalize_sector_code",
    "normalize_symbol",
    "register_builtin_providers",
    "reset_default_client",
    "reset_provider_registry",
]

__version__ = "3.9.2"
