"""Daily-loop hook for the shadow Final Board (opt-in, default OFF).

The daily pipeline calls :func:`run_shadow_board_daily` *after* the production
brief / hits / picks ledger are written. The hook only **reads** the PIT panel
that the brief was built from and writes under the shadow directory. Any
failure is captured into the returned summary and never raised — the
production chain must not be blocked by the shadow chain (ADR 0093 §8).

Enable via ``run_daily_pipeline(shadow_board=True)``, CLI ``--shadow-board`` or
env ``STOCK_PLATFORM_SHADOW_BOARD=1``. Default stays off.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Mapping

ENV_SHADOW_BOARD = "STOCK_PLATFORM_SHADOW_BOARD"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Panel columns forwarded into the shadow universe rows.
_PANEL_KEYS = (
    "close",
    "amount",
    "vol20",
    "rev_chg",
    "ma20",
    "ma60",
    "rs20",
    "trend_up",
    "pct_chg",
    "main_net",
)


def shadow_board_enabled(
    flag: bool | None = None, *, env: Mapping[str, str] | None = None
) -> bool:
    """Explicit flag wins; otherwise ``STOCK_PLATFORM_SHADOW_BOARD``; default False."""
    if flag is not None:
        return bool(flag)
    src = env if env is not None else os.environ
    return str(src.get(ENV_SHADOW_BOARD) or "").strip().lower() in _TRUTHY


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _code6(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def panel_to_shadow_universe(
    panel: Any,
    *,
    name_map: Mapping[str, str] | None = None,
    industry_map: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """PIT cross-section panel (DataFrame or row list) → shadow universe rows.

    Names come from ``name_map`` (code6 or raw symbol key). A row without a name
    keeps ``name=""`` so ``secondary_pick`` rejects it (fail-closed, no guess).
    """
    if panel is None:
        return []
    if hasattr(panel, "to_dict"):
        records = panel.to_dict(orient="records")
    else:
        records = [dict(r) for r in panel if isinstance(r, Mapping)]
    names = dict(name_map or {})
    inds = dict(industry_map or {})
    out: list[dict[str, Any]] = []
    for rec in records:
        sym = str(rec.get("symbol") or rec.get("code") or "").strip()
        code = _code6(sym)
        if not code:
            continue
        row: dict[str, Any] = {"code": code, "symbol": sym}
        for key in _PANEL_KEYS:
            if key in rec:
                row[key] = _clean(rec.get(key))
        name = names.get(code) or names.get(sym) or rec.get("name") or ""
        row["name"] = str(name or "").strip()
        ind = inds.get(code) or inds.get(sym) or rec.get("industry")
        if ind:
            row["industry"] = str(ind)
        out.append(row)
    return out


def run_shadow_board_daily(
    *,
    asof: str,
    panel: Any,
    name_map: Mapping[str, str] | None = None,
    industry_map: Mapping[str, str] | None = None,
    shadow_dir: Path | str | None = None,
    top_k: int = 8,
    reason_provider: Any = None,
    **hooks: Any,
) -> dict[str, Any]:
    """Best-effort: build + write the shadow board; return a manifest summary."""
    try:
        from .ledger import default_shadow_dir
        from .pipeline import run_shadow_board

        universe = panel_to_shadow_universe(
            panel, name_map=name_map, industry_map=industry_map
        )
        payload = run_shadow_board(
            universe,
            asof=asof,
            top_k=top_k,
            shadow_dir=shadow_dir or default_shadow_dir(),
            write=True,
            reason_provider=reason_provider,
            **hooks,
        )
        schools = payload.get("schools") or {}
        # Independent forward ledger (isolated from recommend_decisions.jsonl).
        perf_meta: dict[str, Any]
        try:
            from .performance import log_shadow_board

            logged = log_shadow_board(
                payload, shadow_dir=shadow_dir or default_shadow_dir()
            )
            perf_meta = {"ok": True, "logged": len(logged)}
        except Exception as exc:  # noqa: BLE001 — ledger failure never blocks
            perf_meta = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
        return {
            "ok": True,
            "performanceLedger": perf_meta,
            "status": payload.get("status"),
            "finalCount": len(payload.get("finalBoard") or []),
            "universeSize": len(universe),
            "schools": {
                sid: {
                    "status": (pool or {}).get("status"),
                    "candidates": len((pool or {}).get("candidates") or []),
                }
                for sid, pool in schools.items()
            },
            "ledgerPath": payload.get("ledgerPath"),
            "excludedFromPerformance": True,
            "shadowOnly": True,
        }
    except Exception as exc:  # noqa: BLE001 — shadow chain never blocks production
        return {
            "ok": False,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "excludedFromPerformance": True,
            "shadowOnly": True,
        }


__all__ = [
    "ENV_SHADOW_BOARD",
    "panel_to_shadow_universe",
    "run_shadow_board_daily",
    "shadow_board_enabled",
]
