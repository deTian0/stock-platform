"""Hit tracking — ``X3``: port the ``a-stock-engine`` daily hit cycle to the platform DB.

Rule (single definition; mirrors ``a-stock-engine/src/pick_tracker.py``)::

    first hit for (code, session_type)          → starts a cycle
        cycle_id    = pick_date
        cycle_start = pick_date
        cycle_end   = pick_date + ``cycle_calendar_days`` (default 14)
        cycle_hits  = 1 ; cumulative = 1 ; is_cycle_start = True
    re-hit while pick_date <= active cycle_end  → extend the *same* cycle
        cycle_end   = pick_date + ``cycle_calendar_days``   (sliding window)
        cycle_hits += 1 ; is_cycle_start = False ; total_cycles unchanged
    re-hit after the cycle window closed        → start a *new* cycle
    same (code, session_type, pick_date) twice  → counted once (dedup)

The engine documents "10 交易日周期 + 14 天延期": it approximates 10 trading
days as 14 **calendar** days (``CYCLE_CALENDAR_DAYS = 14``) and *slides* the
window 14 calendar days on every in-window re-hit. This module keeps that exact
behaviour so the two lines never drift; the only hardening is a hard
``UNIQUE(code, session_type, pick_date)`` in place of the engine's read-then-insert
dedup (fail-closed against concurrent writers).

Three cumulative queries (``X3`` acceptance)::

    pre_market           per-code cumulative hits for the pre-market session
    post_market          per-code cumulative hits for the post-market session
    pre_market_in_cycle  per-code hits inside the *active* pre-market cycle

Storage is the shared platform SQLite (``STOCK_PLATFORM_DB_URL`` / ADR 0049),
same file the brief archive uses — see ADR 0057.

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import unquote, urlparse

from .rankings import BOARD_SLUGS, QUALITY_KEY, code_key

PRE_MARKET = "pre_market"
POST_MARKET = "post_market"
HIT_SESSION_TYPES: tuple[str, ...] = (PRE_MARKET, POST_MARKET)

# engine: CYCLE_TRADING_DAYS = 10, CYCLE_CALENDAR_DAYS = 14 ("10 交易日 ≈ 14 自然日")
DEFAULT_CYCLE_CALENDAR_DAYS = 14

ENV_DB_URL = "STOCK_PLATFORM_DB_URL"
DEFAULT_DB_URL = "sqlite:///./data/stock_platform.db"

# engine category labels (②A 质量榜 / ②B 短线榜 / ③C 观察名单 …)
CATEGORY_QUALITY = QUALITY_KEY

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hit_tracking (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  code           TEXT    NOT NULL,
  name           TEXT,
  session_type   TEXT    NOT NULL,
  pick_date      TEXT    NOT NULL,
  category       TEXT,
  cycle_id       TEXT,
  cycle_start    TEXT,
  cycle_end      TEXT,
  cycle_hits     INTEGER NOT NULL DEFAULT 1,
  cumulative     INTEGER NOT NULL DEFAULT 1,
  is_cycle_start INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT    NOT NULL,
  UNIQUE(code, session_type, pick_date)
);
CREATE INDEX IF NOT EXISTS idx_hit_tracking_date  ON hit_tracking(pick_date);
CREATE INDEX IF NOT EXISTS idx_hit_tracking_code  ON hit_tracking(code, session_type);
CREATE INDEX IF NOT EXISTS idx_hit_tracking_cycle ON hit_tracking(cycle_id);

CREATE TABLE IF NOT EXISTS hit_summary (
  code               TEXT    NOT NULL,
  name               TEXT,
  session_type       TEXT    NOT NULL,
  cumulative_hits    INTEGER NOT NULL DEFAULT 0,
  active_cycle_id    TEXT,
  active_cycle_hits  INTEGER NOT NULL DEFAULT 0,
  active_cycle_start TEXT,
  active_cycle_end   TEXT,
  total_cycles       INTEGER NOT NULL DEFAULT 0,
  last_pick_date     TEXT,
  first_pick_date    TEXT,
  updated_at         TEXT    NOT NULL,
  PRIMARY KEY (code, session_type)
);
CREATE INDEX IF NOT EXISTS idx_hit_summary_session
  ON hit_summary(session_type, cumulative_hits DESC);
"""


@dataclass(frozen=True)
class HitTrackingConfig:
    """Cycle length in **calendar** days (engine approximation of 10 sessions)."""

    cycle_calendar_days: int = DEFAULT_CYCLE_CALENDAR_DAYS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def norm_hit_code(value: Any) -> str:
    """6-digit numeric core of any code form (``600519.SH`` / ``600519`` / ``sh600519``)."""
    core = code_key(value)
    if core:
        return core
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6) if digits else ""


def _clean_name(name: Any, code: str) -> str:
    if name is None or str(name).strip().lower() in {"", "nan", "none"}:
        return code
    return str(name).strip()


def apply_hit(
    current: Mapping[str, Any] | None,
    *,
    code: str,
    name: str | None,
    session_type: str,
    pick_date: str,
    config: HitTrackingConfig | None = None,
) -> tuple[dict[str, Any], bool]:
    """Single definition of the cycle rule.

    ``current`` is the existing ``hit_summary`` row (or ``None`` for a first hit).
    Returns ``(updated_summary_state, is_cycle_start)``. Pure — no I/O.
    """
    cfg = config or HitTrackingConfig()
    span = timedelta(days=int(cfg.cycle_calendar_days))
    pd_ = _parse_date(pick_date)
    display_name = _clean_name(name, code)

    if current is None:
        return (
            {
                "code": code,
                "name": display_name,
                "session_type": session_type,
                "cumulative_hits": 1,
                "active_cycle_id": pd_.isoformat(),
                "active_cycle_hits": 1,
                "active_cycle_start": pd_.isoformat(),
                "active_cycle_end": (pd_ + span).isoformat(),
                "total_cycles": 1,
                "last_pick_date": pd_.isoformat(),
                "first_pick_date": pd_.isoformat(),
            },
            True,
        )

    cumulative = int(current.get("cumulative_hits") or 0) + 1
    active_end = current.get("active_cycle_end")
    in_window = bool(active_end) and pd_ <= _parse_date(active_end)

    if in_window:
        return (
            {
                "code": code,
                "name": display_name,
                "session_type": session_type,
                "cumulative_hits": cumulative,
                "active_cycle_id": current.get("active_cycle_id"),
                "active_cycle_hits": int(current.get("active_cycle_hits") or 0) + 1,
                "active_cycle_start": current.get("active_cycle_start"),
                "active_cycle_end": (pd_ + span).isoformat(),
                "total_cycles": int(current.get("total_cycles") or 0),
                "last_pick_date": pd_.isoformat(),
                "first_pick_date": current.get("first_pick_date") or pd_.isoformat(),
            },
            False,
        )

    return (
        {
            "code": code,
            "name": display_name,
            "session_type": session_type,
            "cumulative_hits": cumulative,
            "active_cycle_id": pd_.isoformat(),
            "active_cycle_hits": 1,
            "active_cycle_start": pd_.isoformat(),
            "active_cycle_end": (pd_ + span).isoformat(),
            "total_cycles": int(current.get("total_cycles") or 0) + 1,
            "last_pick_date": pd_.isoformat(),
            "first_pick_date": current.get("first_pick_date") or pd_.isoformat(),
        },
        True,
    )


class HitTrackingRepository(Protocol):
    """Storage port for hit tracking — keep SQL out of the pipeline / routes."""

    def record(
        self,
        *,
        code: str,
        session_type: str,
        pick_date: str,
        name: str | None = None,
        category: str | None = None,
        config: HitTrackingConfig | None = None,
    ) -> dict[str, Any] | None: ...

    def summary(
        self, *, session_type: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]: ...

    def details(
        self,
        *,
        code: str | None = None,
        session_type: str | None = None,
        category: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_state(self, code: str, session_type: str) -> dict[str, Any] | None: ...


def resolve_hit_db_path(db_url: str | None = None) -> str | Path:
    """Parse the platform DB URL to a sqlite path (kept identical to persistence)."""
    raw = (db_url if db_url is not None else os.environ.get(ENV_DB_URL) or DEFAULT_DB_URL).strip()
    if not raw:
        raw = DEFAULT_DB_URL
    if raw == ":memory:" or raw.endswith(":///:memory:") or raw.endswith(":/:memory:"):
        return ":memory:"
    if "://" not in raw:
        return Path(raw)
    parsed = urlparse(raw)
    if parsed.scheme not in {"sqlite", "file"}:
        raise ValueError(f"unsupported DB URL scheme {parsed.scheme!r}; hit tracking uses sqlite://…")
    path = unquote(parsed.path or "")
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        path = f"{parsed.netloc}{path}"
    if path in {"", "/", "/:memory:"}:
        return ":memory:"
    if path.startswith("/") and len(path) > 1 and path[2:3] == ":":
        return Path(path[1:])
    if path.startswith("/./") or path.startswith("/../"):
        return Path(path[1:])
    if path.startswith("/") and not path.startswith("//"):
        if raw.startswith("sqlite:////"):
            return Path(path)
        if os.name == "nt":
            return Path(path.lstrip("/"))
        return Path(path)
    return Path(path.lstrip("/") if path.startswith("/") else path)


class SqliteHitTrackingRepository:
    """SQLite adapter over the shared platform DB. Connection details stay here."""

    def __init__(self, db_url: str | Path | None = None) -> None:
        if isinstance(db_url, Path):
            self._path: str | Path = db_url
            self.db_url = f"sqlite:///{db_url.as_posix()}"
        else:
            url = db_url if db_url is not None else (os.environ.get(ENV_DB_URL) or DEFAULT_DB_URL)
            self.db_url = url
            self._path = resolve_hit_db_path(url)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._path == ":memory:":
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

    # -- writes -----------------------------------------------------------
    def _record_conn(
        self,
        conn: sqlite3.Connection,
        *,
        code: str,
        session_type: str,
        pick_date: str,
        name: str | None,
        category: str | None,
        config: HitTrackingConfig | None,
    ) -> dict[str, Any] | None:
        exists = conn.execute(
            "SELECT id FROM hit_tracking WHERE code=? AND session_type=? AND pick_date=?",
            (code, session_type, pick_date),
        ).fetchone()
        if exists is not None:
            return None  # same-day dedup (also enforced by UNIQUE)

        row = conn.execute(
            "SELECT * FROM hit_summary WHERE code=? AND session_type=?",
            (code, session_type),
        ).fetchone()
        current = dict(row) if row is not None else None
        state, is_cycle_start = apply_hit(
            current,
            code=code,
            name=name,
            session_type=session_type,
            pick_date=pick_date,
            config=config,
        )
        now = _utcnow_iso()
        conn.execute(
            """
            INSERT INTO hit_summary (
              code, name, session_type, cumulative_hits, active_cycle_id,
              active_cycle_hits, active_cycle_start, active_cycle_end,
              total_cycles, last_pick_date, first_pick_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, session_type) DO UPDATE SET
              name=excluded.name,
              cumulative_hits=excluded.cumulative_hits,
              active_cycle_id=excluded.active_cycle_id,
              active_cycle_hits=excluded.active_cycle_hits,
              active_cycle_start=excluded.active_cycle_start,
              active_cycle_end=excluded.active_cycle_end,
              total_cycles=excluded.total_cycles,
              last_pick_date=excluded.last_pick_date,
              first_pick_date=excluded.first_pick_date,
              updated_at=excluded.updated_at
            """,
            (
                state["code"],
                state["name"],
                state["session_type"],
                state["cumulative_hits"],
                state["active_cycle_id"],
                state["active_cycle_hits"],
                state["active_cycle_start"],
                state["active_cycle_end"],
                state["total_cycles"],
                state["last_pick_date"],
                state["first_pick_date"],
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO hit_tracking (
              code, name, session_type, pick_date, category, cycle_id,
              cycle_start, cycle_end, cycle_hits, cumulative, is_cycle_start, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state["code"],
                state["name"],
                session_type,
                pick_date,
                category,
                state["active_cycle_id"],
                state["active_cycle_start"],
                state["active_cycle_end"],
                state["active_cycle_hits"],
                state["cumulative_hits"],
                1 if is_cycle_start else 0,
                now,
            ),
        )
        return {
            "code": state["code"],
            "name": state["name"],
            "sessionType": session_type,
            "pickDate": pick_date,
            "category": category,
            "cycleId": state["active_cycle_id"],
            "cycleStart": state["active_cycle_start"],
            "cycleEnd": state["active_cycle_end"],
            "cycleHits": state["active_cycle_hits"],
            "cumulative": state["cumulative_hits"],
            "isCycleStart": bool(is_cycle_start),
        }

    def record(
        self,
        *,
        code: str,
        session_type: str,
        pick_date: str,
        name: str | None = None,
        category: str | None = None,
        config: HitTrackingConfig | None = None,
    ) -> dict[str, Any] | None:
        norm = norm_hit_code(code)
        if not norm:
            raise ValueError(f"invalid hit code: {code!r}")
        if session_type not in HIT_SESSION_TYPES:
            raise ValueError(
                f"session_type must be one of {HIT_SESSION_TYPES}, got {session_type!r}"
            )
        day = _parse_date(pick_date).isoformat()
        conn = self._connect()
        try:
            detail = self._record_conn(
                conn,
                code=norm,
                session_type=session_type,
                pick_date=day,
                name=name,
                category=category,
                config=config,
            )
            conn.commit()
            return detail
        finally:
            if self._path != ":memory:":
                conn.close()

    def record_many(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        session_type: str,
        pick_date: str | None = None,
        config: HitTrackingConfig | None = None,
    ) -> dict[str, Any]:
        """Batch record; one commit. Returns ``{"recorded", "skipped", "details"}``."""
        if session_type not in HIT_SESSION_TYPES:
            raise ValueError(
                f"session_type must be one of {HIT_SESSION_TYPES}, got {session_type!r}"
            )
        day = _parse_date(pick_date or date.today().isoformat()).isoformat()
        details: list[dict[str, Any]] = []
        skipped = 0
        conn = self._connect()
        try:
            for entry in entries:
                code = entry.get("code") or entry.get("symbol") or entry.get("ts_code")
                norm = norm_hit_code(code)
                if not norm:
                    skipped += 1
                    continue
                detail = self._record_conn(
                    conn,
                    code=norm,
                    session_type=session_type,
                    pick_date=day,
                    name=entry.get("name"),
                    category=entry.get("category"),
                    config=config,
                )
                if detail is None:
                    skipped += 1
                else:
                    details.append(detail)
            conn.commit()
        finally:
            if self._path != ":memory:":
                conn.close()
        return {"recorded": len(details), "skipped": skipped, "details": details}

    # -- reads ------------------------------------------------------------
    def get_state(self, code: str, session_type: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM hit_summary WHERE code=? AND session_type=?",
                (norm_hit_code(code), session_type),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            if self._path != ":memory:":
                conn.close()

    def summary(
        self, *, session_type: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM hit_summary"
        params: list[Any] = []
        if session_type:
            sql += " WHERE session_type=?"
            params.append(session_type)
        sql += " ORDER BY session_type, cumulative_hits DESC, code"
        if limit is not None and int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            if self._path != ":memory:":
                conn.close()

    def active_cycles(
        self, *, session_type: str = PRE_MARKET, asof: str | None = None
    ) -> list[dict[str, Any]]:
        day = _parse_date(asof or date.today().isoformat()).isoformat()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM hit_summary WHERE session_type=? AND active_cycle_end >= ? "
                "ORDER BY active_cycle_hits DESC, cumulative_hits DESC, code",
                (session_type, day),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._path != ":memory:":
                conn.close()

    def details(
        self,
        *,
        code: str | None = None,
        session_type: str | None = None,
        category: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM hit_tracking"
        clauses: list[str] = []
        params: list[Any] = []
        if code:
            clauses.append("code=?")
            params.append(norm_hit_code(code))
        if session_type:
            clauses.append("session_type=?")
            params.append(session_type)
        if category:
            clauses.append("category=?")
            params.append(category)
        if start:
            clauses.append("pick_date>=?")
            params.append(_parse_date(start).isoformat())
        if end:
            clauses.append("pick_date<=?")
            params.append(_parse_date(end).isoformat())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY pick_date DESC, session_type, code"
        if limit is not None and int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        conn = self._connect()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            if self._path != ":memory:":
                conn.close()


_REPO_CACHE: dict[str, SqliteHitTrackingRepository] = {}


def open_hit_repository(db_url: str | Path | None = None) -> SqliteHitTrackingRepository:
    """Open (and cache) the default SQLite hit-tracking repository."""
    if isinstance(db_url, Path):
        key = str(db_url.resolve())
        repo = _REPO_CACHE.get(key)
        if repo is None:
            repo = SqliteHitTrackingRepository(db_url)
            _REPO_CACHE[key] = repo
        return repo
    url = db_url if db_url is not None else (os.environ.get(ENV_DB_URL) or DEFAULT_DB_URL)
    repo = _REPO_CACHE.get(url)
    if repo is None:
        repo = SqliteHitTrackingRepository(url)
        _REPO_CACHE[url] = repo
    return repo


def reset_hit_repository_cache() -> None:
    """Test helper — drop cached repositories."""
    _REPO_CACHE.clear()


# ---------------------------------------------------------------------------
# high-level helpers
# ---------------------------------------------------------------------------

# boards tracked by default: the pre-market recommendation head (``picks`` == ②A).
DEFAULT_TRACK_BOARDS: tuple[str, ...] = ("quality",)


def _board_items(brief: Mapping[str, Any], slug: str) -> list[dict[str, Any]]:
    boards = ((brief.get("rankings") or {}).get("boards") or {})
    board = boards.get(slug) or {}
    items = board.get("items") or []
    return [it for it in items if isinstance(it, Mapping)]


def track_brief_hits(
    repo: HitTrackingRepository,
    brief: Mapping[str, Any],
    *,
    boards: Sequence[str] = DEFAULT_TRACK_BOARDS,
    session_type: str = PRE_MARKET,
    pick_date: str | None = None,
    config: HitTrackingConfig | None = None,
) -> dict[str, Any]:
    """Track a brief's recommendation boards as hits.

    ``asof`` of the brief is the hit date (``pick_date`` overrides). Boards are
    resolved by slug (``quality`` / ``short_term`` / ``watchlist``); each item's
    ``symbol`` becomes the code and the board's engine key becomes ``category``.
    Empty boards contribute nothing (never fabricated).
    """
    day = pick_date or str(brief.get("asof") or "")[:10]
    if not day:
        raise ValueError("brief.asof is required to track hits")
    slug_to_key = {v: k for k, v in BOARD_SLUGS.items()}
    entries: list[dict[str, Any]] = []
    for slug in boards:
        for it in _board_items(brief, slug):
            entries.append(
                {
                    "code": it.get("symbol"),
                    "name": it.get("name"),
                    "category": slug_to_key.get(slug, slug),
                }
            )
    if entries and hasattr(repo, "record_many"):
        result = repo.record_many(  # type: ignore[attr-defined]
            entries, session_type=session_type, pick_date=day, config=config
        )
    else:
        details: list[dict[str, Any]] = []
        skipped = 0
        for e in entries:
            got = repo.record(
                code=str(e.get("code") or ""),
                name=e.get("name"),
                category=e.get("category"),
                session_type=session_type,
                pick_date=day,
                config=config,
            )
            if got is None:
                skipped += 1
            else:
                details.append(got)
        result = {"recorded": len(details), "skipped": skipped, "details": details}
    result["sessionType"] = session_type
    result["pickDate"] = day
    result["boards"] = list(boards)
    return result


def hit_tracking_snapshot(
    repo: HitTrackingRepository,
    *,
    asof: str | None = None,
    cycle_top_n: int = 10,
) -> dict[str, Any]:
    """The three cumulative queries (``X3`` acceptance) in one payload."""
    day = _parse_date(asof or date.today().isoformat()).isoformat()
    out: dict[str, Any] = {
        "asof": day,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }
    for st in HIT_SESSION_TYPES:
        rows = repo.summary(session_type=st)
        out[st] = {
            "sessionType": st,
            "codeCount": len(rows),
            "cumulativeHits": sum(int(r.get("cumulative_hits") or 0) for r in rows),
            "totalCycles": sum(int(r.get("total_cycles") or 0) for r in rows),
            "activeCodeCount": sum(
                1 for r in rows if (r.get("active_cycle_end") or "") >= day
            ),
            "lastPickDate": max((r.get("last_pick_date") or "" for r in rows), default=None)
            or None,
        }
    active = repo.active_cycles(session_type=PRE_MARKET, asof=day)
    out["pre_market_in_cycle"] = {
        "sessionType": PRE_MARKET,
        "asof": day,
        "codeCount": len(active),
        "cycleHits": sum(int(r.get("active_cycle_hits") or 0) for r in active),
        "items": [
            {
                "code": r.get("code"),
                "name": r.get("name"),
                "cycleHits": int(r.get("active_cycle_hits") or 0),
                "cumulativeHits": int(r.get("cumulative_hits") or 0),
                "cycleStart": r.get("active_cycle_start"),
                "cycleEnd": r.get("active_cycle_end"),
            }
            for r in active[: int(cycle_top_n)]
        ],
    }
    return out


def format_hit_report(
    repo: HitTrackingRepository,
    *,
    asof: str | None = None,
    top_n: int = 10,
) -> str:
    """Render the three cumulative views as markdown (never blank)."""
    day = _parse_date(asof or date.today().isoformat()).isoformat()
    lines = [f"# 命中追踪（{day} · SIMULATE · 非投资建议）", ""]
    for st, label in ((PRE_MARKET, "盘前"), (POST_MARKET, "盘后")):
        rows = [r for r in repo.summary(session_type=st) if int(r.get("cumulative_hits") or 0)]
        lines.append(f"## {label}累计命中（{len(rows)} 只）")
        lines.append("")
        if not rows:
            lines.append("_无（fail-closed：不生成占位条目）_")
            lines.append("")
            continue
        lines.append("| 代码 | 名称 | 累计命中 | 周期数 | 当前周期内 | 周期截止 | 最近命中 |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in rows[: int(top_n)]:
            lines.append(
                "| {c} | {n} | {cum} | {cy} | {ch} | {ce} | {last} |".format(
                    c=r.get("code"),
                    n=r.get("name") or r.get("code"),
                    cum=r.get("cumulative_hits"),
                    cy=r.get("total_cycles"),
                    ch=r.get("active_cycle_hits"),
                    ce=r.get("active_cycle_end") or "-",
                    last=r.get("last_pick_date") or "-",
                )
            )
        lines.append("")
    active = repo.active_cycles(session_type=PRE_MARKET, asof=day)
    lines.append(f"## 盘前周期内命中（{len(active)} 只）")
    lines.append("")
    if not active:
        lines.append("_当前无活动周期（所有周期均已结束）_")
    else:
        lines.append("| 代码 | 名称 | 周期内命中 | 累计 | 周期开始 | 周期截止 |")
        lines.append("|---|---|---|---|---|---|")
        for r in active[: int(top_n)]:
            lines.append(
                "| {c} | {n} | {ch} | {cum} | {cs} | {ce} |".format(
                    c=r.get("code"),
                    n=r.get("name") or r.get("code"),
                    ch=r.get("active_cycle_hits"),
                    cum=r.get("cumulative_hits"),
                    cs=r.get("active_cycle_start") or "-",
                    ce=r.get("active_cycle_end") or "-",
                )
            )
    lines.append("")
    return "\n".join(lines) + "\n"


__all__ = [
    "CATEGORY_QUALITY",
    "DEFAULT_CYCLE_CALENDAR_DAYS",
    "DEFAULT_TRACK_BOARDS",
    "HIT_SESSION_TYPES",
    "POST_MARKET",
    "PRE_MARKET",
    "HitTrackingConfig",
    "HitTrackingRepository",
    "SqliteHitTrackingRepository",
    "apply_hit",
    "format_hit_report",
    "hit_tracking_snapshot",
    "norm_hit_code",
    "open_hit_repository",
    "reset_hit_repository_cache",
    "resolve_hit_db_path",
    "track_brief_hits",
]
