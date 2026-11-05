"""S2-P1 — daily event/theme cross-section snapshots for the shadow chain.

Plan: ``docs/plans/s2-event-theme-data.md`` §2 S2-P1 (forward accumulation).

What it does (only when the shadow board runs in the daily loop):

1. Pulls today's **market-wide** cross-sections through ``AStockHttpProvider``
   whose HTTP goes through ``em_get`` (the single East Money throttle):

   - ``lhb``            whole-market 龙虎榜 for ``TRADE_DATE == asof``
   - ``concept_rank``   concept boards ranked by main net inflow (snapshot)
   - ``industry_rank``  industry boards ranked by main net inflow (snapshot)
   - ``unlock``         whole-market lockup calendar ``asof ≤ FREE_DATE ≤ asof+30``

2. Writes ``<shadow_dir>/s2_snapshots/s2_snapshot_{asof}.json`` atomically
   (tmp + replace). A same-asof rerun reuses an ``ok`` snapshot with **zero**
   network; a ``partial`` / ``failed`` one is refetched and overwritten.

3. Converts the snapshot into the existing ``school_s2_theme`` DI hooks.

Hard rules:

- **Fail-soft**: every public function here never raises. Failures land in the
  snapshot ``sources.*.status`` / ``status`` and are surfaced as notes.
- **Budget**: logical EM requests per calendar day (Asia/Shanghai) are capped by
  ``STOCK_PLATFORM_S2_EM_BUDGET`` (default 300), tracked across reruns in
  ``s2_snapshots/_budget.json``. Typical usage is 4 requests/run.
- **PIT**: board rankings are vendor *current* snapshots; they are used only when
  the vendor update time falls on ``asof`` (``pitOk``). Never replayed into
  history — the walk-forward backtest gets no snapshot, so S2 stays empty there.
- Writes only under the shadow dir (``_assert_shadow_path``); never ``market.db``.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from .ledger import _assert_shadow_path, default_shadow_dir

ENV_S2_SNAPSHOT = "STOCK_PLATFORM_S2_SNAPSHOT"
ENV_S2_EM_BUDGET = "STOCK_PLATFORM_S2_EM_BUDGET"
DEFAULT_DAILY_BUDGET = 300
S2_SNAPSHOT_SUBDIR = "s2_snapshots"
BUDGET_LEDGER_NAME = "_budget.json"
SNAPSHOT_SCHEMA_VERSION = 1

UNLOCK_FORWARD_DAYS = 30
# Unlock events at/above this share of float are passed to S2 as soft excludes.
UNLOCK_HEAVY_RATIO = 0.05
BOARD_RANK_LIMIT = 100
HOT_CONCEPT_TOP = 20
HOT_INDUSTRY_TOP = 10
DATACENTER_PAGE_SIZE = 500
DATACENTER_MAX_PAGES = 4

SOURCE_IDS: tuple[str, ...] = ("lhb", "concept_rank", "industry_rank", "unlock")

_CN_TZ = ZoneInfo("Asia/Shanghai")
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})
_TEST_MARKERS = ("PYTEST_CURRENT_TEST", "PYTEST_VERSION")

GetJson = Callable[..., Any]


class S2BudgetExceeded(RuntimeError):
    """Raised inside the budgeted fetcher; always caught in this module."""


def s2_snapshot_enabled(
    flag: bool | None = None, *, env: Mapping[str, str] | None = None
) -> bool:
    """Whether the daily shadow run may hit the network for S2 snapshots.

    Explicit flag wins → ``STOCK_PLATFORM_S2_SNAPSHOT`` (1/0) → default **on**,
    except under the replay preset (CI zero public net) or pytest.
    An existing snapshot file is always readable regardless of this switch.
    """
    if flag is not None:
        return bool(flag)
    src = env if env is not None else os.environ
    raw = str(src.get(ENV_S2_SNAPSHOT) or "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    if str(src.get("STOCK_PLATFORM_PROVIDER_PRESET") or "").strip().lower() == "replay":
        return False
    return not any(str(src.get(m) or "").strip() for m in _TEST_MARKERS)


def daily_budget_limit(env: Mapping[str, str] | None = None) -> int:
    src = env if env is not None else os.environ
    raw = str(src.get(ENV_S2_EM_BUDGET) or "").strip()
    if not raw:
        return DEFAULT_DAILY_BUDGET
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_DAILY_BUDGET


def snapshot_dir(shadow_dir: Path | str | None = None) -> Path:
    root = Path(shadow_dir) if shadow_dir is not None else default_shadow_dir()
    return root / S2_SNAPSHOT_SUBDIR


def snapshot_path(asof: str, shadow_dir: Path | str | None = None) -> Path:
    return snapshot_dir(shadow_dir) / f"s2_snapshot_{str(asof)[:10]}.json"


def load_s2_snapshot(asof: str, shadow_dir: Path | str | None = None) -> dict[str, Any] | None:
    """Read an existing snapshot; missing / corrupt → ``None`` (never raises)."""
    try:
        path = snapshot_path(asof, shadow_dir)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or str(data.get("asof") or "")[:10] != str(asof)[:10]:
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
class _BudgetedGetJson:
    """Counts every logical EM request; refuses once the remaining budget is used."""

    def __init__(self, inner: GetJson, remaining: int) -> None:
        self._inner = inner
        self.remaining = max(0, int(remaining))
        self.used = 0

    def __call__(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self.used >= self.remaining:
            raise S2BudgetExceeded(
                f"S2 东财请求预算已用尽（本次剩余 {self.remaining}）"
            )
        self.used += 1
        return self._inner(url, params=params)


def _em_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Default transport: process-wide ``em_get`` (throttle + circuit + retries)."""
    from stock_platform_providers import em_get

    resp = em_get(url, params=params)
    if isinstance(resp, dict):
        return resp
    return resp.json()


def _read_budget_ledger(sdir: Path) -> dict[str, int]:
    path = sdir / BUDGET_LEDGER_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in data.items():
        try:
            out[str(k)[:10]] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _write_json_atomic(path: Path, payload: Any, *, shadow_root: Path) -> None:
    _assert_shadow_path(path, shadow_root=shadow_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Collect
# --------------------------------------------------------------------------- #
def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


def _rank_source(out: Mapping[str, Any], asof: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    boards = [b for b in (out.get("boards") or []) if isinstance(b, Mapping)]
    updated = str(out.get("updated_at") or "") or None
    pit_ok = bool(updated) and updated[:10] == asof
    meta = {
        "status": "ok" if (boards and pit_ok) else ("stale" if boards else "empty"),
        "count": len(boards),
        "updatedAt": updated,
        "pitOk": pit_ok,
    }
    if boards and not pit_ok:
        meta["note"] = f"板块排名更新时间 {updated} 不在 asof={asof}，非 PIT，不进 S2"
    return meta, [dict(b) for b in boards]


def collect_s2_snapshot(
    asof: str,
    *,
    shadow_dir: Path | str | None = None,
    get_json: GetJson | None = None,
    daily_budget: int | None = None,
    enabled: bool | None = None,
    refresh: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Fetch (or reuse) the S2 snapshot for ``asof``. **Never raises.**

    Returns the snapshot dict (with ``reused`` / ``written`` flags). When the
    network is disabled and no file exists → ``status="disabled"`` (not written).
    """
    day = str(asof)[:10]
    try:
        root = Path(shadow_dir) if shadow_dir is not None else default_shadow_dir()
        sdir = snapshot_dir(root)
        path = snapshot_path(day, root)
        existing = load_s2_snapshot(day, root)
        if existing is not None and existing.get("status") == "ok" and not refresh:
            return {**existing, "reused": True, "written": False, "path": str(path)}
        if not s2_snapshot_enabled(enabled):
            if existing is not None:
                return {**existing, "reused": True, "written": False, "path": str(path)}
            return {
                "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
                "asof": day,
                "status": "disabled",
                "reason": "S2 快照联网关闭（replay / pytest / STOCK_PLATFORM_S2_SNAPSHOT=0）且无落盘快照",
                "reused": False,
                "written": False,
                "path": str(path),
            }

        run_day = (today or datetime.now(_CN_TZ).date()).isoformat()
        limit = daily_budget_limit() if daily_budget is None else max(0, int(daily_budget))
        ledger = _read_budget_ledger(sdir)
        used_before = int(ledger.get(run_day, 0))
        fetcher = _BudgetedGetJson(get_json or _em_get_json, limit - used_before)

        from stock_platform_providers.astock_http import AStockHttpProvider

        provider = AStockHttpProvider(get_json=fetcher)
        asof_d = date.fromisoformat(day)
        sources: dict[str, dict[str, Any]] = {}
        lhb_rows: list[dict[str, Any]] = []
        unlock_rows: list[dict[str, Any]] = []
        boards: dict[str, list[dict[str, Any]]] = {"concept": [], "industry": []}

        def _guard(sid: str, fn: Callable[[], None]) -> None:
            try:
                fn()
            except S2BudgetExceeded as exc:
                sources[sid] = {"status": "budget_exceeded", "count": 0, "error": _err(exc)}
            except Exception as exc:  # noqa: BLE001 — one source never sinks the rest
                sources[sid] = {"status": "failed", "count": 0, "error": _err(exc)}

        def _lhb() -> None:
            out = provider.get_lhb_daily(
                asof_d, page_size=DATACENTER_PAGE_SIZE, max_pages=DATACENTER_MAX_PAGES
            )
            recs = [r for r in (out.get("records") or []) if r.get("date") == day]
            lhb_rows.extend(recs)
            sources["lhb"] = {
                "status": "ok" if recs else "empty",
                "count": len(recs),
                "symbols": len({r.get("symbol") for r in recs}),
                "truncated": bool(out.get("truncated")),
            }

        def _rank(kind: str) -> Callable[[], None]:
            def run() -> None:
                out = provider.get_board_rank(kind, limit=BOARD_RANK_LIMIT)
                meta, rows = _rank_source(out, day)
                boards[kind] = rows
                sources[f"{kind}_rank"] = meta

            return run

        def _unlock() -> None:
            out = provider.get_unlock_calendar(
                asof_d,
                asof_d + timedelta(days=UNLOCK_FORWARD_DAYS),
                page_size=DATACENTER_PAGE_SIZE,
                max_pages=DATACENTER_MAX_PAGES,
            )
            evs = list(out.get("events") or [])
            unlock_rows.extend(evs)
            sources["unlock"] = {
                "status": "ok" if evs else "empty",
                "count": len(evs),
                "truncated": bool(out.get("truncated")),
                "window": [out.get("start"), out.get("end")],
            }

        _guard("lhb", _lhb)
        _guard("concept_rank", _rank("concept"))
        _guard("industry_rank", _rank("industry"))
        _guard("unlock", _unlock)

        statuses = [sources.get(s, {}).get("status") for s in SOURCE_IDS]
        bad = {"failed", "budget_exceeded"}
        if all(st in bad for st in statuses):
            status = "failed"
        elif all(st == "ok" for st in statuses):
            status = "ok"
        else:
            status = "partial"
        used_total = used_before + fetcher.used
        snapshot: dict[str, Any] = {
            "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
            "kind": "s2_snapshot",
            "asof": day,
            "status": status,
            "fetchedAt": datetime.now(_CN_TZ).isoformat(timespec="seconds"),
            "provider": "astock_http",
            "transport": "em_get",
            "budget": {
                "dailyLimit": limit,
                "runDate": run_day,
                "usedThisRun": fetcher.used,
                "usedToday": used_total,
                "exceeded": any(st == "budget_exceeded" for st in statuses),
            },
            "sources": sources,
            "lhb": lhb_rows,
            "boards": boards,
            "unlock": unlock_rows,
            "units": {
                "amount": "元",
                "pct": "小数（0.0268 = 2.68%）",
                "unlockShares": "万股",
                "unlockRatio": "小数（占流通股）",
            },
            "pit": {
                "lhb": "TRADE_DATE == asof（盘后公布；仅可用于 asof 次日入场）",
                "boards": "vendor 当前快照；仅当 updatedAt 日期 == asof 才进 S2",
                "unlock": "当前公告的解禁日程（日程若修订可能有前视，仅作软排除）",
            },
            "excludedFromPerformance": True,
            "shadowOnly": True,
        }
        written = False
        write_error: str | None = None
        try:
            _write_json_atomic(path, snapshot, shadow_root=root)
            written = True
        except Exception as exc:  # noqa: BLE001
            write_error = _err(exc)
        try:
            ledger[run_day] = used_total
            keep = dict(sorted(ledger.items())[-60:])
            _write_json_atomic(sdir / BUDGET_LEDGER_NAME, keep, shadow_root=root)
        except Exception:  # noqa: BLE001 — budget ledger best-effort
            pass
        out = {**snapshot, "reused": False, "written": written, "path": str(path)}
        if write_error:
            out["writeError"] = write_error
        return out
    except Exception as exc:  # noqa: BLE001 — shadow chain never blocks
        return {
            "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
            "asof": day,
            "status": "failed",
            "error": _err(exc),
            "reused": False,
            "written": False,
        }


# --------------------------------------------------------------------------- #
# Snapshot → S2 hooks
# --------------------------------------------------------------------------- #
def _code6(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else ""


def _usable(snapshot: Mapping[str, Any], sid: str) -> bool:
    return str(((snapshot.get("sources") or {}).get(sid) or {}).get("status")) == "ok"


def s2_hooks_from_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Map a snapshot into ``school_s2_theme`` DI kwargs (only PIT-usable parts).

    Always includes ``s2_snapshot_meta`` when a snapshot is given so the S2 pool
    can explain itself. Never raises.
    """
    if not snapshot:
        return {}
    try:
        hooks: dict[str, Any] = {"s2_snapshot_meta": s2_snapshot_summary(snapshot)}
        day = str(snapshot.get("asof") or "")[:10]
        if _usable(snapshot, "lhb"):
            seen: set[str] = set()
            lhb: list[dict[str, Any]] = []
            for r in snapshot.get("lhb") or []:
                code = _code6((r or {}).get("symbol"))
                if code and (r or {}).get("date") == day and code not in seen:
                    seen.add(code)
                    lhb.append({"symbol": code})
            if lhb:
                hooks["lhb"] = lhb
        boards = snapshot.get("boards") or {}
        if _usable(snapshot, "concept_rank"):
            hot = [
                b
                for b in boards.get("concept") or []
                if (b.get("main_net") or 0) > 0 and _code6(b.get("lead_stock"))
            ][:HOT_CONCEPT_TOP]
            if hot:
                hooks["concept_blocks"] = {
                    "boards": [
                        {"name": b.get("name"), "lead_stock": _code6(b.get("lead_stock"))}
                        for b in hot
                    ]
                }
        if _usable(snapshot, "industry_rank"):
            rows = [
                {"sector_name": b.get("name"), "main_net": b.get("main_net")}
                for b in boards.get("industry") or []
                if b.get("name")
            ][:HOT_INDUSTRY_TOP]
            if rows:
                hooks["sector_fund_flow"] = rows
        if _usable(snapshot, "unlock"):
            heavy: dict[str, list[dict[str, Any]]] = {}
            for ev in snapshot.get("unlock") or []:
                code = _code6((ev or {}).get("symbol"))
                ratio = (ev or {}).get("ratio")
                if code and isinstance(ratio, (int, float)) and ratio >= UNLOCK_HEAVY_RATIO:
                    heavy.setdefault(code, []).append({"date": ev.get("date"), "ratio": ratio})
            if heavy:
                hooks["unlock"] = [{"symbol": c, "upcoming": evs} for c, evs in heavy.items()]
        return hooks
    except Exception:  # noqa: BLE001
        return {}


def s2_snapshot_summary(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compact, JSON-safe summary for the shadow payload / daily report."""
    if not snapshot:
        return {"status": "missing"}
    sources = snapshot.get("sources") or {}
    return {
        "asof": snapshot.get("asof"),
        "status": snapshot.get("status"),
        "path": snapshot.get("path"),
        "reused": bool(snapshot.get("reused")),
        "written": bool(snapshot.get("written")),
        "budget": snapshot.get("budget"),
        "sources": {
            sid: {
                k: v
                for k, v in (sources.get(sid) or {}).items()
                if k in {"status", "count", "pitOk", "truncated", "error"}
            }
            for sid in SOURCE_IDS
            if sid in sources
        },
        **({"error": snapshot.get("error")} if snapshot.get("error") else {}),
        **({"reason": snapshot.get("reason")} if snapshot.get("reason") else {}),
    }


__all__ = [
    "DEFAULT_DAILY_BUDGET",
    "ENV_S2_EM_BUDGET",
    "ENV_S2_SNAPSHOT",
    "S2_SNAPSHOT_SUBDIR",
    "S2BudgetExceeded",
    "collect_s2_snapshot",
    "daily_budget_limit",
    "load_s2_snapshot",
    "s2_hooks_from_snapshot",
    "s2_snapshot_enabled",
    "s2_snapshot_summary",
    "snapshot_path",
]
