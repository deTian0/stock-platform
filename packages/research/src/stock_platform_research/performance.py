"""Recommend decision performance — JSONL log + settled metrics.

Aligned with TradingAgents ``performance.py`` naming/口径:

- ``direction_accuracy`` — only directional ratings (Buy/Sell); Hold excluded.
  Long needs positive return; short needs negative. Prefer alpha when present.
- ``avg_return`` / ``median_return`` — holding-period absolute returns.
- ``up_rate`` — fraction of positive raw returns (describes the name, not judgment quality).
- ``outperform_rate`` — fraction of positive alpha when alpha is present.

This is **not** a portfolio backtest: overlapping windows, no costs, no annualization.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

Rating = str

# Direction: long=+1, short=-1, Hold=0 (excluded from direction_accuracy).
_RATING_DIRECTION: dict[str, int] = {
    "Buy": 1,
    "Overweight": 1,
    "Hold": 0,
    "Underweight": -1,
    "Sell": -1,
}

MIN_MEANINGFUL_SAMPLE = 20


def _parse_pct(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text or text.lower() in {"null", "none", "pending"}:
        return None
    try:
        return float(text) / 100.0
    except ValueError:
        return None


def format_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100.0:.2f}%"


def parse_holding_days(value: Any) -> int | None:
    """Parse ``5d`` / ``5`` holding tags."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


@dataclass
class DecisionRecord:
    date: str
    symbol: str
    rating: str
    raw_return: float
    alpha_return: float | None = None
    holding_days: int | None = None
    source: str | None = None
    rank: int | None = None
    score: float | None = None


@dataclass
class GroupStats:
    count: int = 0
    up_rate: float | None = None
    outperform_rate: float | None = None
    direction_accuracy: float | None = None
    directional_count: int = 0
    avg_return: float | None = None
    median_return: float | None = None
    avg_alpha: float | None = None
    best: float | None = None
    worst: float | None = None
    sample_note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def append_jsonl(path: str | Path, record: Mapping[str, Any]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(record), ensure_ascii=False) + "\n")
    return out


def brief_picks_to_pending(
    brief: Mapping[str, Any],
    *,
    holding: str = "5d",
    rating: str = "Buy",
    source: str = "brief",
) -> list[dict[str, Any]]:
    """Map a pre-market brief TopN to pending decision rows."""
    asof = str(brief.get("asof") or "")[:10]
    rows: list[dict[str, Any]] = []
    for pick in brief.get("picks") or []:
        sym = str(pick.get("symbol") or "").strip()
        if not sym:
            continue
        rows.append(
            {
                "date": asof,
                "symbol": sym,
                "rating": rating,
                "raw": None,
                "alpha": None,
                "holding": holding,
                "pending": True,
                "source": source,
                "rank": pick.get("rank"),
                "score": pick.get("composite_score"),
            }
        )
    return rows


def log_brief_decisions(
    path: str | Path,
    brief: Mapping[str, Any],
    *,
    holding: str = "5d",
    rating: str = "Buy",
    skip_existing: bool = True,
) -> list[dict[str, Any]]:
    """Append pending TopN rows; optionally skip date+symbol already in the log.

    ``skip_existing=True`` (default) keeps regenerating the same asof from
    duplicating samples in ``#performance``.
    """
    rows = brief_picks_to_pending(brief, holding=holding, rating=rating)
    if not rows:
        return []
    existing: set[tuple[str, str]] = set()
    if skip_existing:
        log_path = Path(path)
        if log_path.is_file():
            for e in load_jsonl(log_path):
                d = str(e.get("date") or "")[:10]
                s = str(e.get("symbol") or e.get("ticker") or "").strip()
                if d and s:
                    existing.add((d, s))
    appended: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("date") or "")[:10], str(row.get("symbol") or "").strip())
        if skip_existing and key in existing:
            continue
        append_jsonl(path, row)
        appended.append(row)
        existing.add(key)
    return appended


def settled_records(entries: Sequence[Mapping[str, Any]]) -> list[DecisionRecord]:
    """Keep settled rows with parseable raw returns; skip pending / bad parses."""
    out: list[DecisionRecord] = []
    for e in entries:
        if e.get("pending"):
            continue
        raw = _parse_pct(e.get("raw"))
        if raw is None:
            continue
        out.append(
            DecisionRecord(
                date=str(e.get("date") or ""),
                symbol=str(e.get("symbol") or e.get("ticker") or ""),
                rating=str(e.get("rating") or "Unknown"),
                raw_return=raw,
                alpha_return=_parse_pct(e.get("alpha")),
                holding_days=parse_holding_days(e.get("holding")),
                source=str(e["source"]) if e.get("source") is not None else None,
                rank=int(e["rank"]) if e.get("rank") is not None else None,
                score=float(e["score"]) if e.get("score") is not None else None,
            )
        )
    return out


def compute_performance(records: Sequence[DecisionRecord]) -> GroupStats:
    if not records:
        return GroupStats(sample_note="no settled decisions")
    raws = [r.raw_return for r in records]
    alphas = [r.alpha_return for r in records if r.alpha_return is not None]
    directional = [r for r in records if _RATING_DIRECTION.get(r.rating, 0) != 0]
    hits = 0
    for r in directional:
        direction = _RATING_DIRECTION[r.rating]
        ret = r.alpha_return if r.alpha_return is not None else r.raw_return
        if ret * direction > 0:
            hits += 1
    note = None
    if len(records) < MIN_MEANINGFUL_SAMPLE:
        note = (
            f"sample_size={len(records)} < {MIN_MEANINGFUL_SAMPLE}; "
            "ratios are noisy — do not over-interpret"
        )
    return GroupStats(
        count=len(records),
        up_rate=sum(1 for v in raws if v > 0) / len(raws),
        outperform_rate=(sum(1 for v in alphas if v > 0) / len(alphas) if alphas else None),
        direction_accuracy=(hits / len(directional) if directional else None),
        directional_count=len(directional),
        avg_return=statistics.fmean(raws),
        median_return=statistics.median(raws),
        avg_alpha=statistics.fmean(alphas) if alphas else None,
        best=max(raws),
        worst=min(raws),
        sample_note=note,
    )


def performance_summary(
    path: str | Path | None = None,
    *,
    entries: Sequence[Mapping[str, Any]] | None = None,
    recent_days: int = 5,
) -> dict[str, Any]:
    rows = list(entries) if entries is not None else load_jsonl(path or "")
    pending = sum(1 for e in rows if e.get("pending"))
    records = settled_records(rows)
    stats = compute_performance(records)
    holdings = [r.holding_days for r in records if r.holding_days]
    recent = _recent_direction_accuracy(records, recent_days=max(1, int(recent_days)))
    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "logPath": str(path) if path else None,
        "totalEntries": len(rows),
        "pendingCount": pending,
        "settledCount": stats.count,
        "avgHoldingDays": statistics.fmean(holdings) if holdings else None,
        "metrics": stats.as_dict(),
        "recentDays": recent,
        "metricDefinitions": {
            "direction_accuracy": (
                "Share of directional ratings where sign(return)*direction > 0; "
                "Hold excluded; prefer alpha over raw when present."
            ),
            "avg_return": "Mean holding-period absolute return (raw).",
            "up_rate": "Share of positive raw returns (name path, not judgment quality).",
            "outperform_rate": "Share of positive alpha when alpha is present.",
            "recentDays": (
                "Per-day direction_accuracy for the latest N distinct settled dates "
                "(same 口径 as metrics.direction_accuracy)."
            ),
        },
        "disclaimer": "Research metrics only; not investment advice; overlapping windows; no costs.",
    }


def _recent_direction_accuracy(
    records: Sequence[DecisionRecord],
    *,
    recent_days: int = 5,
) -> list[dict[str, Any]]:
    """Latest N distinct decision dates with per-day direction_accuracy."""
    by_date: dict[str, list[DecisionRecord]] = {}
    for r in records:
        by_date.setdefault(r.date, []).append(r)
    dates = sorted(by_date.keys(), reverse=True)[:recent_days]
    out: list[dict[str, Any]] = []
    for d in sorted(dates):
        day_stats = compute_performance(by_date[d])
        out.append(
            {
                "date": d,
                "settledCount": day_stats.count,
                "direction_accuracy": day_stats.direction_accuracy,
            }
        )
    return out


GetDaily = Callable[..., list[dict[str, Any]]]


def _trading_closes(
    bars: Sequence[Mapping[str, Any]],
    *,
    start: date,
    holding_days: int,
) -> tuple[float, float, int] | None:
    """Return (entry_close, exit_close, actual_days) for holding_days sessions after start."""
    ordered = sorted(
        (b for b in bars if str(b.get("date", ""))[:10] >= start.isoformat()),
        key=lambda b: str(b.get("date", ""))[:10],
    )
    closes: list[tuple[str, float]] = []
    for b in ordered:
        c = b.get("close")
        if c is None:
            continue
        closes.append((str(b.get("date", ""))[:10], float(c)))
    # Prefer bar on signal date as entry; else first available on/after.
    entry_idx = None
    for i, (d, _) in enumerate(closes):
        if d >= start.isoformat():
            entry_idx = i
            break
    if entry_idx is None:
        return None
    exit_idx = entry_idx + int(holding_days)
    if exit_idx >= len(closes):
        return None
    return closes[entry_idx][1], closes[exit_idx][1], holding_days


def settle_pending_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    get_daily: GetDaily | None = None,
    returns: Mapping[tuple[str, str], float] | None = None,
    alpha_returns: Mapping[tuple[str, str], float] | None = None,
    end_buffer_calendar_days: int = 40,
) -> list[dict[str, Any]]:
    """Settle pending rows using injected returns map or get_daily closes.

    ``returns`` keys are ``(date, symbol)`` → raw holding-period return as float.
    """
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        if not row.get("pending"):
            out.append(row)
            continue
        key = (str(row.get("date") or "")[:10], str(row.get("symbol") or ""))
        raw_f: float | None = None
        if returns is not None and key in returns:
            raw_f = float(returns[key])
        elif get_daily is not None:
            holding = parse_holding_days(row.get("holding")) or 5
            asof = date.fromisoformat(key[0])
            end = asof + timedelta(days=end_buffer_calendar_days)
            try:
                bars = get_daily([key[1]], start=asof, end=end)
            except Exception:  # noqa: BLE001 — missing bars / fixture → stay pending
                out.append(row)
                continue
            pair = _trading_closes(bars, start=asof, holding_days=holding)
            if pair is not None:
                entry_c, exit_c, _ = pair
                if entry_c:
                    raw_f = exit_c / entry_c - 1.0
        if raw_f is None:
            out.append(row)
            continue
        row["raw"] = format_pct(raw_f)
        if alpha_returns is not None and key in alpha_returns:
            row["alpha"] = format_pct(float(alpha_returns[key]))
        row["pending"] = False
        out.append(row)
    return out


def rewrite_jsonl(path: str | Path, entries: Iterable[Mapping[str, Any]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(dict(e), ensure_ascii=False) + "\n" for e in entries)
    out.write_text(text, encoding="utf-8")
    return out


def settle_performance_log(
    path: str | Path,
    *,
    get_daily: GetDaily | None = None,
    returns: Mapping[tuple[str, str], float] | None = None,
    alpha_returns: Mapping[tuple[str, str], float] | None = None,
    end_buffer_calendar_days: int = 40,
    recent_days: int = 5,
) -> dict[str, Any]:
    """Settle pending JSONL rows in-place when subsequent bars exist.

    Reuses ``settle_pending_entries`` + ``direction_accuracy`` 口径; never invents
    returns when bars are missing (rows stay pending).
    """
    log_path = Path(path)
    entries = load_jsonl(log_path)
    before_pending = sum(1 for e in entries if e.get("pending"))
    settled = settle_pending_entries(
        entries,
        get_daily=get_daily,
        returns=returns,
        alpha_returns=alpha_returns,
        end_buffer_calendar_days=end_buffer_calendar_days,
    )
    after_pending = sum(1 for e in settled if e.get("pending"))
    newly = max(0, before_pending - after_pending)
    if newly > 0:
        rewrite_jsonl(log_path, settled)
    summary = performance_summary(
        log_path, entries=settled, recent_days=recent_days
    )
    summary["settledNewly"] = newly
    summary["autoSettled"] = newly > 0
    summary["pendingBefore"] = before_pending
    return summary


def default_performance_log_path() -> Path:
    """Resolve log path from env or package-local default under cwd."""
    import os

    env = os.environ.get("STOCK_PLATFORM_PERFORMANCE_LOG")
    if env:
        return Path(env)
    return Path.cwd() / "data" / "recommend_decisions.jsonl"


def _fill_as_mapping(fill: Any) -> dict[str, Any]:
    """Duck-type Fill / dict — soft, no hard import of execution package."""
    if isinstance(fill, Mapping):
        return dict(fill)
    if hasattr(fill, "to_dict") and callable(fill.to_dict):
        try:
            data = fill.to_dict()
            if isinstance(data, Mapping):
                return dict(data)
        except Exception:  # noqa: BLE001
            pass
    out: dict[str, Any] = {}
    for key in (
        "symbol",
        "side",
        "qty",
        "price",
        "filled_at",
        "date",
        "ts",
        "raw",
        "return",
        "alpha",
        "holding",
        "fill_id",
        "order_id",
    ):
        if hasattr(fill, key):
            out[key] = getattr(fill, key)
    return out


def _rating_for_side(side: str) -> str | None:
    s = side.strip().lower()
    if s in {"buy", "b", "long"}:
        return "Buy"
    if s in {"sell", "s", "short"}:
        return "Sell"
    return None


def align_fills_to_performance(
    fills: Sequence[Any],
    *,
    holding: str = "5d",
    log_path: str | Path | None = None,
    source: str = "paper_fill",
) -> list[dict[str, Any]]:
    """Map paper / broker fills → performance JSONL decision rows.

    - Buy → rating ``Buy``; Sell → rating ``Sell``.
    - Pending unless ``raw`` / ``return`` is provided on the fill (then settled).
    - Appends via ``append_jsonl`` when ``log_path`` resolves.

    Does **not** change ``direction_accuracy`` 口径 (ADR 0033): still
    directional ratings only, Hold excluded, prefer alpha when present.
    Soft duck-typing avoids a hard dependency cycle on ``stock_platform_execution``.
    """
    path = Path(log_path) if log_path is not None else default_performance_log_path()
    rows: list[dict[str, Any]] = []
    for fill in fills:
        m = _fill_as_mapping(fill)
        sym = str(m.get("symbol") or "").strip()
        if not sym:
            continue
        rating = _rating_for_side(str(m.get("side") or "buy"))
        if rating is None:
            continue
        ts = m.get("date") or m.get("ts") or m.get("filled_at") or ""
        date_s = str(ts)[:10]
        raw_val: Any = m.get("raw")
        if raw_val is None and m.get("return") is not None:
            ret = m["return"]
            raw_val = format_pct(float(ret)) if isinstance(ret, (int, float)) else ret
        pending = raw_val is None
        row: dict[str, Any] = {
            "date": date_s,
            "symbol": sym,
            "rating": rating,
            "raw": raw_val,
            "alpha": m.get("alpha"),
            "holding": str(m.get("holding") or holding),
            "pending": pending,
            "source": source,
            "fill_price": m.get("price"),
            "fill_qty": m.get("qty"),
        }
        append_jsonl(path, row)
        rows.append(row)
    return rows
