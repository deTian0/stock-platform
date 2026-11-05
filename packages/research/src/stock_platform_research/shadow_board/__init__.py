"""Multi-strategy Final Board shadow chain (ADR 0093).

Writes **only** under ``local/shadow/`` (or ``STOCK_PLATFORM_SHADOW_DIR``).
Never mutates production picks / hits / main performance JSONL.
"""

from __future__ import annotations

from .advisory import advisory_set_b
from .ledger import (
    DEFAULT_SHADOW_DIR,
    ENV_SHADOW_DIR,
    default_shadow_dir,
    write_shadow_ledger,
)
from .pipeline import run_shadow_board
from .round2 import SCHOOL_PRIORITY, apply_round2_set_a
from .schools import SCHOOL_IDS, run_round1

__all__ = [
    "DEFAULT_SHADOW_DIR",
    "ENV_SHADOW_DIR",
    "SCHOOL_IDS",
    "SCHOOL_PRIORITY",
    "advisory_set_b",
    "apply_round2_set_a",
    "default_shadow_dir",
    "run_round1",
    "run_shadow_board",
    "write_shadow_ledger",
]
