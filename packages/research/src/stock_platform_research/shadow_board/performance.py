"""Shadow Final Board forward performance ledger (ADR 0093 增补 §生产可用-2).

Single ledger file ``<shadow_dir>/shadow_decisions.jsonl`` — **isolated** from the
production ``recommend_decisions.jsonl`` (path guard below; test-locked).

Two metric sets live side by side on the same settled rows, never blended:

- **Set A** (deterministic arbitration): every Final Board row is a Buy decision;
  metrics = the production ``compute_performance`` 口径 (same holding window,
  same alpha = raw − benchmark), so A is directly comparable to lvrev — but it is
  **reported separately**, never summed into the main metrics.
- **Set B** (Bayesian + LLM advisory): rows carry the advisory rank / score and
  optional predicted win rate. B metrics answer "did the advisory ordering add
  information?" — top-half vs bottom-half of each day's advisory rank, and a
  Brier score when a predicted win rate exists. B never changes which rows exist.

Settlement reuses :func:`stock_platform_research.performance.settle_pending_entries`
(no second holding-window definition). Missing bars ⇒ rows stay pending.

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..performance import (
    DEFAULT_HOLDING,
    GetDaily,
    MIN_MEANINGFUL_SAMPLE,
    append_jsonl,
    compute_performance,
    load_jsonl,
    rewrite_jsonl,
    settle_pending_entries,
    settled_records,
)
from .ledger import FORBIDDEN_BASENAMES, default_shadow_dir

SHADOW_PERF_FILENAME = "shadow_decisions.jsonl"
SHADOW_SOURCE = "shadow_final_board"


def default_shadow_perf_path(shadow_dir: Path | str | None = None) -> Path:
    root = Path(shadow_dir) if shadow_dir is not None else default_shadow_dir()
    return root / SHADOW_PERF_FILENAME


def _guard(path: Path) -> Path:
    if path.name.lower() in FORBIDDEN_BASENAMES:
        raise ValueError(f"影子绩效禁止写入生产账本文件名: {path.name}")
    return path


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def board_to_pending(
    payload: Mapping[str, Any], *, holding: str = DEFAULT_HOLDING
) -> list[dict[str, Any]]:
    """Final Board payload → pending shadow decision rows (A + B fields)."""
    day = str(payload.get("asof") or "")[:10]
    board = [r for r in (payload.get("finalBoard") or []) if isinstance(r, Mapping)]
    advisory = payload.get("advisoryB") or {}
    ranked = [str(c) for c in (advisory.get("rankedCodes") or [])] if advisory else []
    hints = {
        str(h.get("code")): h
        for h in ((advisory.get("rankHints") or []) if advisory else [])
        if isinstance(h, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for rank, r in enumerate(board, start=1):
        code = str(r.get("code") or "").strip()
        if not day or not code:
            continue
        hint = hints.get(code) or {}
        rows.append(
            {
                "date": day,
                "symbol": code,
                "name": r.get("name"),
                "rating": "Buy",
                "raw": None,
                "alpha": None,
                "holding": holding,
                "pending": True,
                "source": SHADOW_SOURCE,
                "rank": rank,
                "score": _num(r.get("score")),
                "school": r.get("school"),
                "schoolHolding": r.get("holdingPeriod"),
                "setA": {"arbiter": "set_a", "passed": True},
                "setB": {
                    "advisoryRank": (ranked.index(code) + 1) if code in ranked else None,
                    "advisoryScore": _num(hint.get("advisoryScore")),
                    "winRate": _num(r.get("winRate") or hint.get("winRate")),
                    "expectedReturn": _num(
                        r.get("expectedReturn") or hint.get("expectedReturn")
                    ),
                },
                "excludedFromPerformance": True,
                "shadowOnly": True,
            }
        )
    return rows


def log_shadow_board(
    payload: Mapping[str, Any],
    *,
    path: Path | str | None = None,
    shadow_dir: Path | str | None = None,
    holding: str = DEFAULT_HOLDING,
) -> list[dict[str, Any]]:
    """Append pending rows; idempotent on ``(date, symbol)``. Empty board ⇒ nothing."""
    p = _guard(Path(path) if path is not None else default_shadow_perf_path(shadow_dir))
    rows = board_to_pending(payload, holding=holding)
    if not rows:
        return []
    existing = {
        (str(e.get("date") or "")[:10], str(e.get("symbol") or ""))
        for e in load_jsonl(p)
    }
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (row["date"], row["symbol"])
        if key in existing:
            continue
        append_jsonl(p, row)
        existing.add(key)
        out.append(row)
    return out


def _parse_pct(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    try:
        return float(text) / 100.0
    except ValueError:
        return None


def _set_b_metrics(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Advisory ordering information content + calibration (never re-admits rows)."""
    settled = [
        e for e in entries if not e.get("pending") and _parse_pct(e.get("raw")) is not None
    ]
    by_day: dict[str, list[Mapping[str, Any]]] = {}
    for e in settled:
        if (e.get("setB") or {}).get("advisoryRank") is not None:
            by_day.setdefault(str(e.get("date"))[:10], []).append(e)
    top: list[float] = []
    bottom: list[float] = []
    for rows in by_day.values():
        if len(rows) < 2:
            continue
        ordered = sorted(rows, key=lambda x: int((x.get("setB") or {})["advisoryRank"]))
        half = len(ordered) // 2
        top += [_parse_pct(x.get("raw")) or 0.0 for x in ordered[:half]]
        bottom += [_parse_pct(x.get("raw")) or 0.0 for x in ordered[len(ordered) - half :]]
    briers: list[float] = []
    for e in settled:
        wr = _num((e.get("setB") or {}).get("winRate"))
        if wr is None or not 0.0 <= wr <= 1.0:
            continue
        outcome = 1.0 if (_parse_pct(e.get("raw")) or 0.0) > 0 else 0.0
        briers.append((wr - outcome) ** 2)
    spread = (
        statistics.fmean(top) - statistics.fmean(bottom) if top and bottom else None
    )
    return {
        "rankedDays": len(by_day),
        "topHalfCount": len(top),
        "topHalfAvgReturn": statistics.fmean(top) if top else None,
        "bottomHalfAvgReturn": statistics.fmean(bottom) if bottom else None,
        "topMinusBottom": spread,
        "winRateSamples": len(briers),
        "brierScore": statistics.fmean(briers) if briers else None,
        "available": bool(top or briers),
        "note": (
            "集 B 只评估顾问排序/胜率是否含信息；不改入选集合；"
            "无顾问字段时 available=false（不编造）"
        ),
    }


def shadow_performance_summary(
    path: Path | str | None = None,
    *,
    shadow_dir: Path | str | None = None,
    entries: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    p = Path(path) if path is not None else default_shadow_perf_path(shadow_dir)
    rows = list(entries) if entries is not None else load_jsonl(p)
    stats = compute_performance(settled_records(rows))
    by_school: dict[str, Any] = {}
    for sid in sorted({str(e.get("school") or "") for e in rows} - {""}):
        recs = settled_records([e for e in rows if str(e.get("school") or "") == sid])
        by_school[sid] = compute_performance(recs).as_dict()
    days = sorted({str(e.get("date") or "")[:10] for e in rows} - {""})
    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "logPath": str(p),
        "shadowOnly": True,
        "excludedFromPerformance": True,
        "notMixedWithMain": True,
        "totalEntries": len(rows),
        "pendingCount": sum(1 for e in rows if e.get("pending")),
        "settledCount": stats.count,
        "decisionDays": len(days),
        "minMeaningfulSample": int(MIN_MEANINGFUL_SAMPLE),
        "sampleSufficient": stats.count >= int(MIN_MEANINGFUL_SAMPLE),
        "setA": {"metrics": stats.as_dict(), "bySchool": by_school},
        "setB": _set_b_metrics(rows),
        "disclaimer": (
            "影子前向账本：与主绩效 recommend_decisions.jsonl 物理隔离、不混算；"
            "持有窗口与 alpha 口径复用主结算单点；非投资建议。"
        ),
    }


def settle_shadow_ledger(
    path: Path | str | None = None,
    *,
    shadow_dir: Path | str | None = None,
    get_daily: GetDaily | None = None,
    returns: Mapping[tuple[str, str], float] | None = None,
    benchmark_get_daily: GetDaily | None = None,
    benchmark_symbol: str | None = None,
    alpha_available: bool = True,
) -> dict[str, Any]:
    """Settle pending shadow rows in place (same window/alpha single point as main)."""
    p = _guard(Path(path) if path is not None else default_shadow_perf_path(shadow_dir))
    entries = load_jsonl(p)
    before = sum(1 for e in entries if e.get("pending"))
    settled = settle_pending_entries(
        entries,
        get_daily=get_daily,
        returns=returns,
        benchmark_get_daily=benchmark_get_daily,
        benchmark_symbol=benchmark_symbol,
        alpha_available=alpha_available,
    )
    after = sum(1 for e in settled if e.get("pending"))
    if settled != entries:
        rewrite_jsonl(p, settled)
    summary = shadow_performance_summary(p, entries=settled)
    summary["settledNewly"] = max(0, before - after)
    return summary


__all__ = [
    "SHADOW_PERF_FILENAME",
    "SHADOW_SOURCE",
    "board_to_pending",
    "default_shadow_perf_path",
    "log_shadow_board",
    "settle_shadow_ledger",
    "shadow_performance_summary",
]
