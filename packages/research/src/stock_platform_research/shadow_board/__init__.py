"""Multi-strategy Final Board shadow chain (ADR 0093).

Writes **only** under ``local/shadow/`` (or ``STOCK_PLATFORM_SHADOW_DIR``).
Never mutates production picks / hits / main performance JSONL.
"""

from __future__ import annotations

from .advisory import advisory_set_b
from .digest_hook import render_shadow_board_appendix, shadow_board_json_path
from .ledger import (
    DEFAULT_SHADOW_DIR,
    ENV_SHADOW_DIR,
    default_shadow_dir,
    write_shadow_ledger,
)
from .performance import (
    SHADOW_PERF_FILENAME,
    board_to_pending,
    default_shadow_perf_path,
    log_shadow_board,
    settle_shadow_ledger,
    shadow_performance_summary,
)
from .pipeline import run_shadow_board
from .reasons import (
    BANNED_PHRASES,
    LLM_REASON_SCHEMA,
    apply_reason_policy,
    build_reason_prompt,
    validate_reason,
)
from .round2 import SCHOOL_PRIORITY, apply_round2_set_a
from .schools import SCHOOL_IDS, run_round1

__all__ = [
    "BANNED_PHRASES",
    "LLM_REASON_SCHEMA",
    "apply_reason_policy",
    "build_reason_prompt",
    "validate_reason",
    "DEFAULT_SHADOW_DIR",
    "ENV_SHADOW_DIR",
    "SCHOOL_IDS",
    "SCHOOL_PRIORITY",
    "advisory_set_b",
    "apply_round2_set_a",
    "default_shadow_dir",
    "render_shadow_board_appendix",
    "run_round1",
    "run_shadow_board",
    "shadow_board_json_path",
    "write_shadow_ledger",
    "SHADOW_PERF_FILENAME",
    "board_to_pending",
    "default_shadow_perf_path",
    "log_shadow_board",
    "settle_shadow_ledger",
    "shadow_performance_summary",
]
