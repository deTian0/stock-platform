"""Research kernels: lvrev scoring, entry gates, PIT backtest helpers."""

from .batch import score_cross_section, score_cross_section_csv
from .brief import brief_to_orders, build_premarket_brief, write_brief_csv
from .gates import apply_entry_gates, apply_risk_gates
from .lvrev import W_DEFAULT, W_VALUE, factor_scores, score_lvrev
from .panel import build_cross_section_panel, panel_to_csv
from .performance import (
    compute_performance,
    default_performance_log_path,
    log_brief_decisions,
    performance_summary,
    settled_records,
)
from .refresh import REFRESH_DATASETS, RefreshReport, run_refresh
from .pit import assert_no_lookahead_columns, run_pit_long_only
from .universe import (
    UniverseEmptyError,
    default_universe_fixture_path,
    load_universe,
    normalize_universe,
)

__all__ = [
    "W_DEFAULT",
    "W_VALUE",
    "UniverseEmptyError",
    "apply_entry_gates",
    "apply_risk_gates",
    "assert_no_lookahead_columns",
    "brief_to_orders",
    "build_cross_section_panel",
    "build_premarket_brief",
    "compute_performance",
    "default_performance_log_path",
    "default_universe_fixture_path",
    "factor_scores",
    "load_universe",
    "log_brief_decisions",
    "normalize_universe",
    "panel_to_csv",
    "performance_summary",
    "REFRESH_DATASETS",
    "RefreshReport",
    "run_refresh",
    "run_pit_long_only",
    "score_cross_section",
    "score_cross_section_csv",
    "score_lvrev",
    "settled_records",
    "write_brief_csv",
]

__version__ = "2.5.0"
