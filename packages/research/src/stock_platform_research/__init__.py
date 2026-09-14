"""Research kernels: lvrev scoring, entry gates, PIT backtest helpers."""

from .batch import score_cross_section, score_cross_section_csv
from .brief import brief_to_orders, build_premarket_brief, write_brief_csv
from .gates import apply_entry_gates, apply_risk_gates
from .lvrev import W_DEFAULT, W_VALUE, factor_scores, score_lvrev
from .panel import build_cross_section_panel, panel_to_csv
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
    "default_universe_fixture_path",
    "factor_scores",
    "load_universe",
    "normalize_universe",
    "panel_to_csv",
    "run_pit_long_only",
    "score_cross_section",
    "score_cross_section_csv",
    "score_lvrev",
    "write_brief_csv",
]

__version__ = "1.18.0"
