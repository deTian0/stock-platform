"""Thin brief repository — SQLite first, dialect kept out of business/routes.

Authority for daily recommend archives (U2). JSON file export remains optional
and is not the sole truth source. See ADR 0049.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import unquote, urlparse

ENV_DB_URL = "STOCK_PLATFORM_DB_URL"
DEFAULT_DB_URL = "sqlite:///./data/stock_platform.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_briefs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asof TEXT NOT NULL UNIQUE,
  provider TEXT,
  universe_tier TEXT,
  symbols_json TEXT,
  picks_json TEXT NOT NULL,
  soft_gates INTEGER,
  gates_relaxed INTEGER,
  data_note TEXT,
  generated_at TEXT,
  environment TEXT NOT NULL DEFAULT 'SIMULATE',
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_briefs_asof ON daily_briefs(asof DESC);
"""


def default_db_url() -> str:
    return (os.environ.get(ENV_DB_URL) or DEFAULT_DB_URL).strip()


def resolve_sqlite_path(db_url: str | None = None) -> str | Path:
    """Parse ``STOCK_PLATFORM_DB_URL`` into a sqlite path or ``:memory:``.

    Accepts ``sqlite:///./data/x.db``, ``sqlite:///:memory:``, or a bare path.
    """
    raw = (db_url if db_url is not None else default_db_url()).strip()
    if not raw:
        raw = DEFAULT_DB_URL
    if raw == ":memory:" or raw.endswith(":///:memory:") or raw.endswith(":/:memory:"):
        return ":memory:"
    if "://" not in raw:
        return Path(raw)
    parsed = urlparse(raw)
    if parsed.scheme not in {"sqlite", "file"}:
        raise ValueError(
            f"unsupported DB URL scheme {parsed.scheme!r}; "
            "U2 uses sqlite://… (PostgreSQL is a later migration target)"
        )
    path = unquote(parsed.path or "")
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        # sqlite:///C:/… on Windows may appear as netloc=C
        path = f"{parsed.netloc}{path}"
    if path in {"", "/", "/:memory:"}:
        return ":memory:"
    # sqlite:///./data/x.db → path="/./data/x.db"
    if path.startswith("/") and len(path) > 1 and path[2:3] == ":":
        # Windows absolute: /C:/Users/...
        return Path(path[1:])
    if path.startswith("/./") or path.startswith("/../"):
        return Path(path[1:])
    if path.startswith("/") and not path.startswith("//"):
        # Relative intent from sqlite:///./… already handled; lone /foo is absolute on Unix.
        # Prefer treating sqlite:///./data as relative; sqlite:////abs as absolute.
        if raw.startswith("sqlite:////"):
            return Path(path)
        # sqlite:///data/x.db → /data/x.db on Unix absolute; on Windows treat as relative.
        if os.name == "nt":
            return Path(path.lstrip("/"))
        return Path(path)
    return Path(path.lstrip("/") if path.startswith("/") else path)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _int_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(int(value))


@dataclass(frozen=True)
class BriefRecord:
    """Normalized row returned by the repository (backend-agnostic)."""

    asof: str
    provider: str | None
    universe_tier: str | None
    symbols: list[str] | None
    picks: list[dict[str, Any]]
    soft_gates: bool | None
    gates_relaxed: bool | None
    data_note: str | None
    generated_at: str | None
    environment: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asof": self.asof,
            "provider": self.provider,
            "universeTier": self.universe_tier,
            "symbols": self.symbols,
            "picks": self.picks,
            "softGates": self.soft_gates,
            "gatesRelaxed": self.gates_relaxed,
            "dataNote": self.data_note,
            "generatedAt": self.generated_at,
            "environment": self.environment,
            "payload": self.payload,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "pickCount": len(self.picks),
        }

    def summary_dict(self) -> dict[str, Any]:
        """List-row shape without full picks/payload (Chinese UI friendly)."""
        return {
            "id": self.id,
            "asof": self.asof,
            "provider": self.provider,
            "universeTier": self.universe_tier,
            "pickCount": len(self.picks),
            "softGates": self.soft_gates,
            "gatesRelaxed": self.gates_relaxed,
            "dataNote": self.data_note,
            "generatedAt": self.generated_at,
            "environment": self.environment,
            "updatedAt": self.updated_at,
        }


class BriefRepository(Protocol):
    """Storage port for daily briefs — keep SQL out of routes/strategy."""

    def save(
        self,
        brief: Mapping[str, Any],
        *,
        symbols: Sequence[str] | None = None,
    ) -> BriefRecord:
        """Upsert by ``asof`` (same-day regenerate overwrites)."""

    def get_by_asof(self, asof: str) -> BriefRecord | None: ...

    def list_recent(self, *, limit: int = 30) -> list[BriefRecord]: ...


class SqliteBriefRepository:
    """SQLite adapter. Connection details stay here for a future PG swap."""

    def __init__(self, db_url: str | Path | None = None) -> None:
        if isinstance(db_url, Path):
            self._path: str | Path = db_url
            self.db_url = f"sqlite:///{db_url.as_posix()}"
        else:
            url = db_url if db_url is not None else default_db_url()
            self.db_url = url
            self._path = resolve_sqlite_path(url)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._path == ":memory:":
            # Keep a single in-memory connection for the repo lifetime.
            conn = getattr(self, "_mem_conn", None)
            if conn is None:
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._mem_conn = conn
            return conn
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            if self._path != ":memory:":
                conn.close()

    def save(
        self,
        brief: Mapping[str, Any],
        *,
        symbols: Sequence[str] | None = None,
    ) -> BriefRecord:
        asof = str(brief.get("asof") or "")[:10]
        if not asof:
            raise ValueError("brief.asof is required to persist")
        picks = list(brief.get("picks") or [])
        # Never persist secrets — only provider name already on the brief.
        payload = dict(brief)
        for key in ("token", "apiKey", "api_key", "authorization"):
            payload.pop(key, None)

        sym_list: list[str] | None
        if symbols is not None:
            sym_list = [str(s).strip() for s in symbols if str(s).strip()]
        else:
            raw_sym = brief.get("symbols")
            if isinstance(raw_sym, str) and raw_sym.strip():
                sym_list = [s.strip() for s in raw_sym.split(",") if s.strip()]
            elif isinstance(raw_sym, (list, tuple)):
                sym_list = [str(s).strip() for s in raw_sym if str(s).strip()]
            else:
                sym_list = None

        now = _utcnow_iso()
        generated_at = brief.get("generatedAt") or now
        environment = str(brief.get("environment") or "SIMULATE")
        provider = brief.get("provider")
        if provider is not None:
            provider = str(provider)

        conn = self._connect()
        try:
            # ON CONFLICT: do not touch created_at (first-write wins).
            conn.execute(
                """
                INSERT INTO daily_briefs (
                  asof, provider, universe_tier, symbols_json, picks_json,
                  soft_gates, gates_relaxed, data_note, generated_at,
                  environment, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asof) DO UPDATE SET
                  provider=excluded.provider,
                  universe_tier=excluded.universe_tier,
                  symbols_json=excluded.symbols_json,
                  picks_json=excluded.picks_json,
                  soft_gates=excluded.soft_gates,
                  gates_relaxed=excluded.gates_relaxed,
                  data_note=excluded.data_note,
                  generated_at=excluded.generated_at,
                  environment=excluded.environment,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (
                    asof,
                    provider,
                    brief.get("universeTier"),
                    json.dumps(sym_list, ensure_ascii=False) if sym_list is not None else None,
                    json.dumps(picks, ensure_ascii=False),
                    _bool_int(brief.get("softGates")),
                    _bool_int(brief.get("gatesRelaxed")),
                    brief.get("dataNote"),
                    generated_at,
                    environment,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            stored = self.get_by_asof(asof)
            assert stored is not None
            return stored
        finally:
            if self._path != ":memory:":
                conn.close()

    def get_by_asof(self, asof: str) -> BriefRecord | None:
        asof_s = str(asof)[:10]
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM daily_briefs WHERE asof = ?",
                (asof_s,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_record(row)
        finally:
            if self._path != ":memory:":
                conn.close()

    def list_recent(self, *, limit: int = 30) -> list[BriefRecord]:
        lim = max(1, min(int(limit), 365))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM daily_briefs ORDER BY asof DESC LIMIT ?",
                (lim,),
            ).fetchall()
            return [_row_to_record(r) for r in rows]
        finally:
            if self._path != ":memory:":
                conn.close()


def _row_to_record(row: sqlite3.Row) -> BriefRecord:
    symbols_raw = row["symbols_json"]
    symbols: list[str] | None = None
    if symbols_raw:
        parsed = json.loads(symbols_raw)
        if isinstance(parsed, list):
            symbols = [str(s) for s in parsed]
    picks = json.loads(row["picks_json"] or "[]")
    payload = json.loads(row["payload_json"] or "{}")
    return BriefRecord(
        id=int(row["id"]) if row["id"] is not None else None,
        asof=str(row["asof"]),
        provider=row["provider"],
        universe_tier=row["universe_tier"],
        symbols=symbols,
        picks=list(picks) if isinstance(picks, list) else [],
        soft_gates=_int_bool(row["soft_gates"]),
        gates_relaxed=_int_bool(row["gates_relaxed"]),
        data_note=row["data_note"],
        generated_at=row["generated_at"],
        environment=str(row["environment"] or "SIMULATE"),
        payload=dict(payload) if isinstance(payload, dict) else {},
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


_REPO_CACHE: dict[str, SqliteBriefRepository] = {}


def open_brief_repository(db_url: str | Path | None = None) -> SqliteBriefRepository:
    """Open (and cache) the default SQLite brief repository."""
    if isinstance(db_url, Path):
        key = str(db_url.resolve())
        repo = _REPO_CACHE.get(key)
        if repo is None:
            repo = SqliteBriefRepository(db_url)
            _REPO_CACHE[key] = repo
        return repo
    url = db_url if db_url is not None else default_db_url()
    repo = _REPO_CACHE.get(url)
    if repo is None:
        repo = SqliteBriefRepository(url)
        _REPO_CACHE[url] = repo
    return repo


def reset_brief_repository_cache() -> None:
    """Test helper — drop cached connections."""
    _REPO_CACHE.clear()
