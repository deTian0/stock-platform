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

# Single point for the default holding tag, shared by log / settle / digest so the
# 记账口径 never drifts (the daily CLI used to log "1d" while the workbench used "5d").
DEFAULT_HOLDING = "5d"

# Alpha benchmark. ``market.db`` stores index series with an SZ suffix (the engine maps
# every 0-prefixed code to SZ), e.g. 中证500 = ``000905.SZ``; 沪深300 (000300) is absent
# from the warehouse, so 中证500 is the default proxy. Override via env.
DEFAULT_BENCHMARK_SYMBOL = "000905"
ENV_BENCHMARK_SYMBOL = "STOCK_PLATFORM_BENCHMARK_SYMBOL"


def resolve_benchmark_symbol() -> str:
    """Benchmark symbol for alpha: env override, else :data:`DEFAULT_BENCHMARK_SYMBOL`."""
    import os

    raw = str(os.environ.get(ENV_BENCHMARK_SYMBOL) or "").strip()
    return raw or DEFAULT_BENCHMARK_SYMBOL


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
    holding: str = DEFAULT_HOLDING,
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
    holding: str = DEFAULT_HOLDING,
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
        "attribution": build_attribution(records),
        "benchmarkSymbol": resolve_benchmark_symbol(),
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
            "winRate": (
                "attribution.winRate — share of positive raw returns across settled rows."
            ),
            "beatBenchmarkRate": (
                "attribution.beatBenchmarkRate — share of positive alpha (raw − benchmark)."
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


def _holding_window(
    bars: Sequence[Mapping[str, Any]],
    *,
    start: date,
    holding_days: int,
) -> tuple[str, float, str, float] | None:
    """(entry_date, entry_close, exit_date, exit_close) for a holding window.

    Entry = first bar on/after ``start``; exit = ``holding_days`` sessions later.
    Reusing this single definition for both the stock and the benchmark is what
    keeps ``raw`` and ``alpha`` on the *same* session window (ADR 0068).
    """
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
    return (
        closes[entry_idx][0],
        closes[entry_idx][1],
        closes[exit_idx][0],
        closes[exit_idx][1],
    )


def _trading_closes(
    bars: Sequence[Mapping[str, Any]],
    *,
    start: date,
    holding_days: int,
) -> tuple[float, float, int] | None:
    """Return (entry_close, exit_close, actual_days); thin view over _holding_window."""
    window = _holding_window(bars, start=start, holding_days=holding_days)
    if window is None:
        return None
    _, entry_c, _, exit_c = window
    return entry_c, exit_c, int(holding_days)


def _safe_daily(
    get_daily: GetDaily, symbol: str, start: date, end: date
) -> list[dict[str, Any]]:
    """Best-effort daily fetch — never raises (missing bars ⇒ empty list)."""
    try:
        return list(get_daily([symbol], start=start, end=end) or [])
    except Exception:  # noqa: BLE001 — any provider failure ⇒ treat as no data
        return []


def _close_on_or_before(bars: Sequence[Mapping[str, Any]], target: str) -> float | None:
    best_date: str | None = None
    best_close: float | None = None
    for b in bars:
        c = b.get("close")
        d = str(b.get("date", ""))[:10]
        if c is None or not d or d > target:
            continue
        if best_date is None or d > best_date:
            best_date, best_close = d, float(c)
    return best_close


def _benchmark_return_for_window(
    bench_bars: Sequence[Mapping[str, Any]],
    *,
    entry_date: str,
    exit_date: str,
) -> float | None:
    """Benchmark return between the entry/exit dates (nearest close on/before each)."""
    entry_c = _close_on_or_before(bench_bars, entry_date)
    exit_c = _close_on_or_before(bench_bars, exit_date)
    if not entry_c or exit_c is None:
        return None
    return exit_c / entry_c - 1.0


def _window_alpha(
    *,
    raw_f: float,
    entry_date: str,
    exit_date: str,
    bench_bars: Sequence[Mapping[str, Any]],
) -> float | None:
    """``alpha = raw − benchmark`` over the same window; None when benchmark missing."""
    bench_ret = _benchmark_return_for_window(
        bench_bars, entry_date=entry_date, exit_date=exit_date
    )
    return None if bench_ret is None else raw_f - bench_ret


def settle_pending_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    get_daily: GetDaily | None = None,
    returns: Mapping[tuple[str, str], float] | None = None,
    alpha_returns: Mapping[tuple[str, str], float] | None = None,
    benchmark_get_daily: GetDaily | None = None,
    benchmark_symbol: str | None = None,
    end_buffer_calendar_days: int = 40,
) -> list[dict[str, Any]]:
    """Settle pending rows using injected returns map or get_daily closes.

    ``returns`` keys are ``(date, symbol)`` → raw holding-period return as float.

    When ``benchmark_get_daily`` is supplied, ``alpha = raw − benchmark`` is computed
    over the **same entry/exit dates** (single window definition, ``_holding_window``).
    Already-settled rows whose ``alpha`` is still null are back-filled the same way, so
    a JSONL written before the benchmark existed catches up on the next settle.
    """
    bench_sym = benchmark_symbol or resolve_benchmark_symbol()
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        holding = parse_holding_days(row.get("holding")) or 5
        key = (str(row.get("date") or "")[:10], str(row.get("symbol") or ""))
        if not row.get("pending"):
            if (
                benchmark_get_daily is not None
                and get_daily is not None
                and row.get("alpha") is None
                and key[0]
            ):
                raw_existing = _parse_pct(row.get("raw"))
                if raw_existing is not None:
                    asof0 = date.fromisoformat(key[0])
                    end0 = asof0 + timedelta(days=end_buffer_calendar_days)
                    win0 = _holding_window(
                        _safe_daily(get_daily, key[1], asof0, end0),
                        start=asof0,
                        holding_days=holding,
                    )
                    if win0 is not None:
                        entry_d0, _, exit_d0, _ = win0
                        alpha0 = _window_alpha(
                            raw_f=raw_existing,
                            entry_date=entry_d0,
                            exit_date=exit_d0,
                            bench_bars=_safe_daily(
                                benchmark_get_daily, bench_sym, asof0, end0
                            ),
                        )
                        if alpha0 is not None:
                            row["alpha"] = format_pct(alpha0)
            out.append(row)
            continue
        raw_f: float | None = None
        alpha_f: float | None = None
        if returns is not None and key in returns:
            raw_f = float(returns[key])
        elif get_daily is not None and key[0]:
            asof = date.fromisoformat(key[0])
            end = asof + timedelta(days=end_buffer_calendar_days)
            win = _holding_window(
                _safe_daily(get_daily, key[1], asof, end),
                start=asof,
                holding_days=holding,
            )
            if win is not None:
                entry_d, entry_c, exit_d, exit_c = win
                if entry_c:
                    raw_f = exit_c / entry_c - 1.0
                    if benchmark_get_daily is not None:
                        alpha_f = _window_alpha(
                            raw_f=raw_f,
                            entry_date=entry_d,
                            exit_date=exit_d,
                            bench_bars=_safe_daily(
                                benchmark_get_daily, bench_sym, asof, end
                            ),
                        )
        if raw_f is None:
            out.append(row)
            continue
        row["raw"] = format_pct(raw_f)
        if alpha_returns is not None and key in alpha_returns:
            row["alpha"] = format_pct(float(alpha_returns[key]))
        elif alpha_f is not None:
            row["alpha"] = format_pct(alpha_f)
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
    benchmark_get_daily: GetDaily | None = None,
    benchmark_symbol: str | None = None,
    end_buffer_calendar_days: int = 40,
    recent_days: int = 5,
) -> dict[str, Any]:
    """Settle pending JSONL rows in-place when subsequent bars exist.

    Reuses ``settle_pending_entries`` + ``direction_accuracy`` 口径; never invents
    returns when bars are missing (rows stay pending). ``benchmark_get_daily`` adds
    ``alpha`` (raw − benchmark) and back-fills alpha on rows settled without it.
    """
    log_path = Path(path)
    entries = load_jsonl(log_path)
    before_pending = sum(1 for e in entries if e.get("pending"))
    before_alpha = sum(1 for e in entries if e.get("alpha") is not None)
    settled = settle_pending_entries(
        entries,
        get_daily=get_daily,
        returns=returns,
        alpha_returns=alpha_returns,
        benchmark_get_daily=benchmark_get_daily,
        benchmark_symbol=benchmark_symbol,
        end_buffer_calendar_days=end_buffer_calendar_days,
    )
    after_pending = sum(1 for e in settled if e.get("pending"))
    after_alpha = sum(1 for e in settled if e.get("alpha") is not None)
    newly = max(0, before_pending - after_pending)
    alpha_newly = max(0, after_alpha - before_alpha)
    if newly > 0 or alpha_newly > 0:
        rewrite_jsonl(log_path, settled)
    summary = performance_summary(
        log_path, entries=settled, recent_days=recent_days
    )
    summary["settledNewly"] = newly
    summary["autoSettled"] = newly > 0
    summary["pendingBefore"] = before_pending
    summary["alphaSettledNewly"] = alpha_newly
    summary["benchmarkSymbol"] = benchmark_symbol or resolve_benchmark_symbol()
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
    holding: str = DEFAULT_HOLDING,
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


# --------------------------------------------------------------------------- #
# PnL attribution (milestone v4.3.0): settled decisions → user-visible returns.
# --------------------------------------------------------------------------- #


def _group_stats(records: Sequence[DecisionRecord]) -> dict[str, Any]:
    if not records:
        return {
            "count": 0,
            "up_rate": None,
            "avg_return": None,
            "median_return": None,
            "avg_alpha": None,
            "outperform_rate": None,
            "best": None,
            "worst": None,
        }
    raws = [r.raw_return for r in records]
    alphas = [r.alpha_return for r in records if r.alpha_return is not None]
    return {
        "count": len(records),
        "up_rate": sum(1 for v in raws if v > 0) / len(raws),
        "avg_return": statistics.fmean(raws),
        "median_return": statistics.median(raws),
        "avg_alpha": statistics.fmean(alphas) if alphas else None,
        "outperform_rate": (
            sum(1 for v in alphas if v > 0) / len(alphas) if alphas else None
        ),
        "best": max(raws),
        "worst": min(raws),
    }


def bucket_by_rank(records: Sequence[DecisionRecord]) -> list[dict[str, Any]]:
    """Settled stats grouped by recommendation ``rank`` (1 = top pick)."""
    groups: dict[int, list[DecisionRecord]] = {}
    for r in records:
        groups.setdefault(r.rank if r.rank is not None else -1, []).append(r)
    out: list[dict[str, Any]] = []
    for rank in sorted(groups):
        label = "未标 rank" if rank < 0 else f"rank {rank}"
        out.append(
            {
                "rank": rank if rank >= 0 else None,
                "label": label,
                **_group_stats(groups[rank]),
            }
        )
    return out


def bucket_by_score(
    records: Sequence[DecisionRecord], *, n_buckets: int = 3
) -> list[dict[str, Any]]:
    """Settled stats grouped by equal-count ``score`` buckets (low → high)."""
    scored = [r for r in records if r.score is not None]
    if not scored:
        return []
    scored.sort(key=lambda r: (r.score, r.date, r.symbol))
    n = max(1, int(n_buckets))
    total = len(scored)
    out: list[dict[str, Any]] = []
    for i in range(n):
        lo = i * total // n
        hi = (i + 1) * total // n
        chunk = scored[lo:hi]
        if not chunk:
            continue
        lo_s = float(chunk[0].score)
        hi_s = float(chunk[-1].score)
        out.append(
            {
                "bucket": i,
                "label": f"[{lo_s:.4f},{hi_s:.4f}]",
                "minScore": lo_s,
                "maxScore": hi_s,
                **_group_stats(chunk),
            }
        )
    return out


def bucket_by_date(records: Sequence[DecisionRecord]) -> list[dict[str, Any]]:
    """Settled stats per decision date (chronological)."""
    groups: dict[str, list[DecisionRecord]] = {}
    for r in records:
        groups.setdefault(r.date, []).append(r)
    return [{"date": d, **_group_stats(groups[d])} for d in sorted(groups)]


def equity_curve(records: Sequence[DecisionRecord]) -> list[dict[str, Any]]:
    """Per-decision equal-weight cumulative return, chronological.

    Holding windows overlap at the decision level, so this is **not** a tradable
    portfolio curve — it answers "is the recommendation logic directionally
    profitable?" (ADR 0068 caveat), not "what would my account look like?".
    """
    ordered = sorted(records, key=lambda r: (r.date, r.symbol))
    cum = 1.0
    out: list[dict[str, Any]] = []
    for r in ordered:
        cum *= 1.0 + r.raw_return
        out.append(
            {
                "date": r.date,
                "symbol": r.symbol,
                "cumulative": cum - 1.0,
            }
        )
    return out


def build_attribution(records: Sequence[DecisionRecord]) -> dict[str, Any]:
    """Return attribution: win rate / avg return / alpha / buckets / equity curve."""
    if not records:
        return {
            "count": 0,
            "winRate": None,
            "avgReturn": None,
            "medianReturn": None,
            "avgAlpha": None,
            "beatBenchmarkRate": None,
            "best": None,
            "worst": None,
            "byRank": [],
            "byScore": [],
            "byDate": [],
            "equityCurve": [],
            "benchmarkSymbol": resolve_benchmark_symbol(),
            "notes": ["no settled decisions"],
        }
    base = _group_stats(records)
    notes: list[str] = []
    if base["count"] < MIN_MEANINGFUL_SAMPLE:
        notes.append(
            f"sample_size={base['count']} < {MIN_MEANINGFUL_SAMPLE}; ratios are noisy "
            "— do not over-interpret"
        )
    if base["avg_alpha"] is None:
        notes.append(
            "alpha 全为 null：settle 时未提供基准（benchmark_get_daily）；"
            f"基准默认 {DEFAULT_BENCHMARK_SYMBOL}，可用 {ENV_BENCHMARK_SYMBOL} 覆盖"
        )
    notes.append(
        "equityCurve 为决策序列等权累计，持有窗口重叠，非可交易组合曲线（不含成本）"
    )
    return {
        "count": base["count"],
        "winRate": base["up_rate"],
        "avgReturn": base["avg_return"],
        "medianReturn": base["median_return"],
        "avgAlpha": base["avg_alpha"],
        "beatBenchmarkRate": base["outperform_rate"],
        "best": base["best"],
        "worst": base["worst"],
        "byRank": bucket_by_rank(records),
        "byScore": bucket_by_score(records),
        "byDate": bucket_by_date(records),
        "equityCurve": equity_curve(records),
        "benchmarkSymbol": resolve_benchmark_symbol(),
        "notes": notes,
    }
