"""Research kernels: lvrev scoring, entry gates, PIT backtest helpers."""

from .batch import score_cross_section, score_cross_section_csv
from .brief import (
    brief_to_orders,
    build_premarket_brief,
    build_reasons_for_row,
    reason_summary,
    write_brief_csv,
)
from .daily_pipeline import DailyPipelineReport, run_daily_pipeline
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
from .strategy_config import (
    StrategyConfig,
    compare_strategy_configs,
    list_strategy_configs,
    load_strategy_config,
    run_strategy_pit,
)
from .universe import (
    UniverseEmptyError,
    default_daily_universe_path,
    default_universe_fixture_path,
    load_universe,
    load_universe_tiers,
    normalize_universe,
    universe_size_guidance,
)

__all__ = [
    "W_DEFAULT",
    "W_VALUE",
    "DailyPipelineReport",
    "StrategyConfig",
    "UniverseEmptyError",
    "apply_entry_gates",
    "apply_risk_gates",
    "assert_no_lookahead_columns",
    "brief_to_orders",
    "build_cross_section_panel",
    "build_premarket_brief",
    "build_reasons_for_row",
    "compare_strategy_configs",
    "compute_performance",
    "default_daily_universe_path",
    "default_performance_log_path",
    "default_universe_fixture_path",
    "factor_scores",
    "list_strategy_configs",
    "load_strategy_config",
    "load_universe",
    "load_universe_tiers",
    "log_brief_decisions",
    "normalize_universe",
    "panel_to_csv",
    "performance_summary",
    "reason_summary",
    "REFRESH_DATASETS",
    "RefreshReport",
    "run_daily_pipeline",
    "run_refresh",
    "run_pit_long_only",
    "run_strategy_pit",
    "score_cross_section",
    "score_cross_section_csv",
    "score_lvrev",
    "settled_records",
    "universe_size_guidance",
    "write_brief_csv",
]

__version__ = "3.2.0"
