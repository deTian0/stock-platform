"""Paper-only execution safety kernel (broker-free)."""

from .admission import evaluate_admission
from .errors import (
    ActivationBlocked,
    DraftBlocked,
    ExecutionError,
    IdempotentReplay,
    ProfileBlocked,
)
from .lifecycle import StrategyLifecycle, build_strategy_spec, strategy_hash
from .paper import PaperLedger
from .profile import default_execution_profile, validate_simulation_profile
from .timing import (
    completed_bar_cutoff,
    execution_window_status,
    planned_execution_date,
    signal_bar_is_completed,
)
from .transactional import (
    EXECUTION_FIELDS,
    MARKET_FIELDS,
    build_pending_rebalance,
    committed_state_after_acceptance,
    compose_calculation_state,
    extract_market_state,
    pending_is_active,
)

__all__ = [
    "ActivationBlocked",
    "DraftBlocked",
    "EXECUTION_FIELDS",
    "ExecutionError",
    "IdempotentReplay",
    "MARKET_FIELDS",
    "PaperLedger",
    "ProfileBlocked",
    "StrategyLifecycle",
    "build_pending_rebalance",
    "build_strategy_spec",
    "committed_state_after_acceptance",
    "completed_bar_cutoff",
    "compose_calculation_state",
    "default_execution_profile",
    "evaluate_admission",
    "execution_window_status",
    "extract_market_state",
    "pending_is_active",
    "planned_execution_date",
    "signal_bar_is_completed",
    "strategy_hash",
    "validate_simulation_profile",
]

__version__ = "1.4.1"
