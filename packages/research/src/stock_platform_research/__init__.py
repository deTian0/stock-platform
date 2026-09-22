"""Research kernels: lvrev scoring, entry gates, PIT backtest helpers."""

from .batch import score_cross_section, score_cross_section_csv
from .brief import (
    brief_to_orders,
    build_premarket_brief,
    build_reasons_for_row,
    reason_summary,
    write_brief_csv,
)
from .brief_review import review_stored_brief
from .rolling_review import run_rolling_recommend_review
from .daily_pipeline import DailyPipelineReport, run_daily_pipeline
from .persistence import (
    BriefRecord,
    BriefRepository,
    SqliteBriefRepository,
    default_db_url,
    open_brief_repository,
    reset_brief_repository_cache,
)
from .gates import apply_entry_gates, apply_risk_gates
from .lvrev import W_DEFAULT, W_VALUE, factor_scores, score_lvrev
from .panel import build_cross_section_panel, build_multi_day_pit_panel, panel_to_csv
from .performance import (
    align_fills_to_performance,
    compute_performance,
    default_performance_log_path,
    log_brief_decisions,
    performance_summary,
    settle_performance_log,
    settled_records,
)
from .portfolio import portfolio_metrics, run_portfolio_pit
from .refresh import REFRESH_DATASETS, RefreshReport, run_refresh
from .pit import assert_no_lookahead_columns, run_pit_long_only
from .strategy_config import (
    StrategyConfig,
    compare_strategy_configs,
    list_strategy_configs,
    load_strategy_config,
    run_strategy_pit,
)
from .strategy_ab import (
    attach_strategy_ab,
    run_strategy_ab_sidecar,
    strategy_ab_enabled,
    strategy_ab_status,
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
from .walkforward import (
    WalkForwardFold,
    aggregate_oos,
    generate_folds,
    summarize_walk_forward,
)
from .empirical_compare import compare_empirical_baseline, extract_engine_fold_returns
from .factor_ic import (
    spearman_rank_ic,
    summarize_factor_ic,
    summarize_factor_ic_from_rows,
)

__all__ = [
    "W_DEFAULT",
    "W_VALUE",
    "BriefRecord",
    "BriefRepository",
    "DailyPipelineReport",
    "SqliteBriefRepository",
    "StrategyConfig",
    "UniverseEmptyError",
    "WalkForwardFold",
    "aggregate_oos",
    "align_fills_to_performance",
    "apply_entry_gates",
    "apply_risk_gates",
    "assert_no_lookahead_columns",
    "attach_strategy_ab",
    "brief_to_orders",
    "build_cross_section_panel",
    "build_multi_day_pit_panel",
    "build_premarket_brief",
    "build_reasons_for_row",
    "compare_empirical_baseline",
    "compare_strategy_configs",
    "compute_performance",
    "default_daily_universe_path",
    "default_db_url",
    "default_performance_log_path",
    "default_universe_fixture_path",
    "extract_engine_fold_returns",
    "factor_scores",
    "generate_folds",
    "list_strategy_configs",
    "load_strategy_config",
    "load_universe",
    "load_universe_tiers",
    "log_brief_decisions",
    "normalize_universe",
    "open_brief_repository",
    "panel_to_csv",
    "performance_summary",
    "portfolio_metrics",
    "reason_summary",
    "REFRESH_DATASETS",
    "RefreshReport",
    "reset_brief_repository_cache",
    "review_stored_brief",
    "run_daily_pipeline",
    "run_portfolio_pit",
    "run_refresh",
    "run_pit_long_only",
    "run_rolling_recommend_review",
    "run_strategy_ab_sidecar",
    "run_strategy_pit",
    "score_cross_section",
    "score_cross_section_csv",
    "score_lvrev",
    "settle_performance_log",
    "settled_records",
    "spearman_rank_ic",
    "strategy_ab_enabled",
    "strategy_ab_status",
    "summarize_factor_ic",
    "summarize_factor_ic_from_rows",
    "summarize_walk_forward",
    "universe_size_guidance",
    "write_brief_csv",
]

__version__ = "3.12.1"
