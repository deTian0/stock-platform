"""U3 skeleton: settle stored brief picks with subsequent daily bars.

Full direction_accuracy / holding matrices stay in ``performance``; this module
only bridges U2 archive → T+N mark for the workbench review API.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Mapping, Sequence

from .performance import format_pct, parse_holding_days

GetDaily = Callable[..., list[dict[str, Any]]]


def _trading_closes_tplus(
    bars: Sequence[Mapping[str, Any]],
    *,
    start: date,
    holding_days: int,
) -> tuple[float, float, str, str] | None:
    """Entry close on/after asof, exit close ``holding_days`` sessions later."""
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
    if not closes:
        return None
    entry_idx = 0
    exit_idx = entry_idx + int(holding_days)
    if exit_idx >= len(closes):
        return None
    return closes[entry_idx][1], closes[exit_idx][1], closes[entry_idx][0], closes[exit_idx][0]


def review_stored_brief(
    record: Mapping[str, Any],
    *,
    get_daily: GetDaily | None = None,
    holding: str = "1d",
    end_buffer_calendar_days: int = 40,
) -> dict[str, Any]:
    """Mark each pick with T+N raw return / direction (Buy assumed).

    Missing subsequent bars → ``pending=True`` (never fill 0 silently).
    """
    asof = str(record.get("asof") or "")[:10]
    holding_days = parse_holding_days(holding) or 1
    picks = list(record.get("picks") or [])
    rows: list[dict[str, Any]] = []
    pending = 0
    settled = 0
    up = 0

    for pick in picks:
        sym = str(pick.get("symbol") or "").strip()
        if not sym:
            continue
        item: dict[str, Any] = {
            "rank": pick.get("rank"),
            "symbol": sym,
            "score": pick.get("composite_score"),
            "holding": f"{holding_days}d",
            "rating": "Buy",
            "pending": True,
            "rawReturn": None,
            "directionOk": None,
            "entryDate": None,
            "exitDate": None,
            "note": None,
        }
        if get_daily is None:
            item["note"] = "无日线源，无法结算"
            pending += 1
            rows.append(item)
            continue
        try:
            asof_d = date.fromisoformat(asof)
            end = asof_d + timedelta(days=end_buffer_calendar_days)
            bars = get_daily([sym], start=asof_d, end=end)
            pair = _trading_closes_tplus(bars, start=asof_d, holding_days=holding_days)
        except Exception as exc:  # noqa: BLE001 — review boundary; keep row pending
            item["note"] = f"行情拉取失败：{type(exc).__name__}"
            pending += 1
            rows.append(item)
            continue
        if pair is None:
            item["note"] = "后续交易日不足，暂未结算"
            pending += 1
            rows.append(item)
            continue
        entry_c, exit_c, entry_d, exit_d = pair
        if not entry_c:
            item["note"] = "入场价缺失"
            pending += 1
            rows.append(item)
            continue
        raw = exit_c / entry_c - 1.0
        item["pending"] = False
        item["rawReturn"] = format_pct(raw)
        item["rawReturnFloat"] = raw
        item["directionOk"] = raw > 0  # Buy / look-long
        item["entryDate"] = entry_d
        item["exitDate"] = exit_d
        settled += 1
        if raw > 0:
            up += 1
        rows.append(item)

    direction_accuracy = (up / settled) if settled else None
    return {
        "asof": asof,
        "holding": f"{holding_days}d",
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "pickCount": len(rows),
        "pendingCount": pending,
        "settledCount": settled,
        "upRate": (up / settled) if settled else None,
        # Align with performance.direction_accuracy (Buy look-long; Hold N/A here).
        "directionAccuracy": direction_accuracy,
        "direction_accuracy": direction_accuracy,
        "metricNote": (
            "direction_accuracy 与 performance 包语义对齐：「看多 Buy」收益>0 算方向对；"
            "Hold 不计；up_rate 只描述涨跌。缺行情为 pending，不静默填 0。"
        ),
        "rows": rows,
        "disclaimer": "推荐复盘研究指标；非投资建议；不复权收盘价；缺失跳过。",
    }
