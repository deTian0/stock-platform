"""Singleton runtime config row in ``stock_platform.db`` (broker / capital / holdings).

ADR 0064 narrative stays in docs; **runtime** suggestions live here and are
editable. ``live_trading_enabled`` is always stored as ``0`` and cannot be
opened by this module (SIMULATE red line).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .persistence import DEFAULT_DB_URL, default_db_url, resolve_sqlite_path

TABLE = "platform_runtime_config"

# Safe product defaults aligned with L1 charter narrative (editable after seed).
DEFAULT_BROKER_SUGGESTION = "华宝证券"
DEFAULT_CAPITAL_LIMIT_CNY = 10000.0
DEFAULT_HOLDINGS_PATH = "./local/holdings.json"
DEFAULT_NOTES = (
    "运行时建议值；文档 ADR 0064 仍是立项叙事。"
    "live_trading_enabled 恒为 0，本表不可解除 SIMULATE 红线。"
)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  broker_suggestion TEXT NOT NULL,
  capital_limit_cny REAL NOT NULL,
  holdings_path TEXT NOT NULL,
  notes TEXT,
  live_trading_enabled INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class RuntimeConfig:
    broker_suggestion: str
    capital_limit_cny: float
    holdings_path: str
    notes: str | None
    live_trading_enabled: bool
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "brokerSuggestion": self.broker_suggestion,
            "capitalLimitCny": self.capital_limit_cny,
            "holdingsPath": self.holdings_path,
            "notes": self.notes,
            "liveTradingEnabled": self.live_trading_enabled,
            "updatedAt": self.updated_at,
        }


def _connect(db_url: str | None = None) -> tuple[sqlite3.Connection, str | Path]:
    url = (db_url if db_url is not None else default_db_url()).strip() or DEFAULT_DB_URL
    path = resolve_sqlite_path(url)
    if path == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn, path


def read_runtime_config(db_url: str | None = None) -> RuntimeConfig | None:
    """Return the singleton row, or ``None`` if missing."""
    conn, _ = _connect(db_url)
    try:
        row = conn.execute(f"SELECT * FROM {TABLE} WHERE id = 1").fetchone()
        if row is None:
            return None
        return RuntimeConfig(
            broker_suggestion=str(row["broker_suggestion"]),
            capital_limit_cny=float(row["capital_limit_cny"]),
            holdings_path=str(row["holdings_path"]),
            notes=row["notes"],
            live_trading_enabled=bool(int(row["live_trading_enabled"])),
            updated_at=str(row["updated_at"]),
        )
    finally:
        conn.close()


def seed_runtime_config(
    db_url: str | None = None,
    *,
    broker_suggestion: str = DEFAULT_BROKER_SUGGESTION,
    capital_limit_cny: float = DEFAULT_CAPITAL_LIMIT_CNY,
    holdings_path: str = DEFAULT_HOLDINGS_PATH,
    notes: str | None = DEFAULT_NOTES,
    force: bool = False,
) -> tuple[RuntimeConfig, bool]:
    """Insert defaults when the row is missing.

    Returns ``(config, created)``. When the row already exists and ``force`` is
    false, returns the existing row and ``created=False`` (idempotent).
    ``live_trading_enabled`` is always written as ``0``.
    """
    if capital_limit_cny <= 0:
        raise ValueError("capital_limit_cny must be positive (fail-closed)")
    broker = str(broker_suggestion or "").strip()
    if not broker:
        raise ValueError("broker_suggestion must be non-empty (fail-closed)")
    holdings = str(holdings_path or "").strip() or DEFAULT_HOLDINGS_PATH

    conn, _ = _connect(db_url)
    try:
        existing = conn.execute(f"SELECT * FROM {TABLE} WHERE id = 1").fetchone()
        if existing is not None and not force:
            return (
                RuntimeConfig(
                    broker_suggestion=str(existing["broker_suggestion"]),
                    capital_limit_cny=float(existing["capital_limit_cny"]),
                    holdings_path=str(existing["holdings_path"]),
                    notes=existing["notes"],
                    live_trading_enabled=bool(int(existing["live_trading_enabled"])),
                    updated_at=str(existing["updated_at"]),
                ),
                False,
            )
        now = _utcnow_iso()
        conn.execute(
            f"""
            INSERT INTO {TABLE} (
              id, broker_suggestion, capital_limit_cny, holdings_path,
              notes, live_trading_enabled, updated_at
            ) VALUES (1, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(id) DO UPDATE SET
              broker_suggestion = excluded.broker_suggestion,
              capital_limit_cny = excluded.capital_limit_cny,
              holdings_path = excluded.holdings_path,
              notes = excluded.notes,
              live_trading_enabled = 0,
              updated_at = excluded.updated_at
            """,
            (broker, float(capital_limit_cny), holdings, notes, now),
        )
        conn.commit()
        return (
            RuntimeConfig(
                broker_suggestion=broker,
                capital_limit_cny=float(capital_limit_cny),
                holdings_path=holdings,
                notes=notes,
                live_trading_enabled=False,
                updated_at=now,
            ),
            True,
        )
    finally:
        conn.close()


__all__ = [
    "DEFAULT_BROKER_SUGGESTION",
    "DEFAULT_CAPITAL_LIMIT_CNY",
    "DEFAULT_HOLDINGS_PATH",
    "DEFAULT_NOTES",
    "RuntimeConfig",
    "read_runtime_config",
    "seed_runtime_config",
]
