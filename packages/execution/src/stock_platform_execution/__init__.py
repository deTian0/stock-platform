"""Paper-only execution safety kernel + SIMULATE broker ports."""

from .admission import evaluate_admission
from .broker import BrokerPort, ExternalSimBroker, PaperBroker, resolve_broker
from .contracts import AccountSnapshot, Fill, OrderIntent, Position
from .errors import (
    ActivationBlocked,
    BrokerConfigError,
    BrokerTransportError,
    DraftBlocked,
    ExecutionError,
    IdempotentReplay,
    ProfileBlocked,
)
from .gated import GatedBroker, assert_sim_gates
from .lifecycle import StrategyLifecycle, build_strategy_spec, strategy_hash
from .paper import PaperLedger
from .profile import default_execution_profile, validate_simulation_profile
from .ths_sim import ExperimentalThsHttpTransport, MockThsTransport, ThsSimBroker
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
    "AccountSnapshot",
    "ActivationBlocked",
    "BrokerConfigError",
    "BrokerPort",
    "BrokerTransportError",
    "DraftBlocked",
    "EXECUTION_FIELDS",
    "ExecutionError",
    "ExperimentalThsHttpTransport",
    "ExternalSimBroker",
    "Fill",
    "GatedBroker",
    "IdempotentReplay",
    "MARKET_FIELDS",
    "MockThsTransport",
    "OrderIntent",
    "PaperBroker",
    "PaperLedger",
    "Position",
    "ProfileBlocked",
    "StrategyLifecycle",
    "ThsSimBroker",
    "assert_sim_gates",
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
    "resolve_broker",
    "signal_bar_is_completed",
    "strategy_hash",
    "validate_simulation_profile",
]

__version__ = "3.9.1"
