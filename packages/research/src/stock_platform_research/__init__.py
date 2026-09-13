"""Research kernels: lvrev scoring, entry gates, PIT backtest helpers."""

from .batch import score_cross_section, score_cross_section_csv
from .gates import apply_entry_gates, apply_risk_gates
from .lvrev import W_DEFAULT, W_VALUE, factor_scores, score_lvrev
from .pit import assert_no_lookahead_columns, run_pit_long_only

__all__ = [
    "W_DEFAULT",
    "W_VALUE",
    "apply_entry_gates",
    "apply_risk_gates",
    "assert_no_lookahead_columns",
    "factor_scores",
    "run_pit_long_only",
    "score_cross_section",
    "score_cross_section_csv",
    "score_lvrev",
]

__version__ = "0.3.2"
