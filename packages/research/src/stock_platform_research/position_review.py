"""Online book review — the **second** caller of :mod:`stock_platform_research.rules` (``B5``).

The backtest path (:func:`backtest.run_portfolio_backtest`) replays history. This
module is the *online / daily* path: given the **current book** and today's
reference close per holding, it says what the rules want done — ``hold`` /
``exit`` / ``trim`` / ``add``.

It does **not** re-implement anything. Every decision is delegated to the shared
rules layer, so the two paths cannot drift apart::

    review_positions(...)  →  rules.evaluate_exit     (same as the backtest)
                              rules.advance_peak
                              rules.evaluate_drift
                              rules.is_limit_down

``V2-code-review-20260905`` §「检查重点」item 5 asked exactly this: 回测与在线规则
是否一致；冷静期、退出条件和持仓偏差是否存在逻辑盲区. ``tests/test_position_review.py``
pins the parity with a differential test (same state ⇒ same reason string).

Pure functions only — no pandas, no I/O, no DB. The optional CLI
(``position_review_cli.py``) owns the read-only ``market.db`` access.

SIMULATE only. ``liveTradingEnabled=False``. Not investment advice.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .rules import (
    CooldownPolicy,
    DriftPolicy,
    ExitPolicy,
    advance_peak,
    evaluate_drift,
    evaluate_exit,
    is_limit_down,
)

# Holding keys accepted on input, most-specific first.
_PRICE_KEYS = ("price", "close", "current_price", "last", "ref_close")
_CODE_KEYS = ("code", "symbol", "ts_code")
_ENTRY_KEYS = ("entry_price", "cost", "cost_price", "avg_price")


def _pick(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for k in keys:
        if row.get(k) is not None:
            return row[k]
    return None


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v  # NaN-safe without importing math


def review_positions(
    holdings: Sequence[Mapping[str, Any]],
    *,
    exit_policy: ExitPolicy | None = None,
    cooldown_policy: CooldownPolicy | None = None,
    drift_policy: DriftPolicy | None = None,
    current_idx: int | None = None,
    asof: str | None = None,
) -> dict[str, Any]:
    """Review the current book and return per-holding actions.

    Each holding is a mapping with:

    ===================  =====================================================
    key                  meaning
    ===================  =====================================================
    ``code``             required, e.g. ``600519.SH``
    ``entry_price``      required, the actual fill / average cost
    ``price``            required, **today's reference close** (aliases accepted)
    ``held_days``        sessions since entry (entry session = 0); default 0
    ``peak``             running peak; default = ``entry_price``
    ``ma20`` / ``ma60``  optional trend inputs for the ``trend_break`` rule
    ``pct_chg``          optional, for the limit-down "can't sell" check
    ``target``           optional override; default from ``ExitPolicy.target_price``
    ``weight`` /         optional, only needed for the 持仓偏差 rule
    ``target_weight``
    ``last_exit_idx``    optional, only needed for the 冷静期 rule
    ===================  =====================================================

    Actions: ``exit`` (a rule fired — ``reason`` is the shared string), ``trim`` /
    ``add`` (weight drift), ``hold``, or ``pending`` (missing price ⇒ no opinion,
    never a fabricated instruction). A limit-down seal on an ``exit`` sets
    ``deferred=True`` (the sell rolls to the next session, mirroring the backtest).

    Returns a ``SIMULATE`` payload; empty input is **fail-closed**
    (``ok=False``, no rows invented).
    """
    exit_policy = exit_policy or ExitPolicy()
    cooldown_policy = cooldown_policy or CooldownPolicy()
    drift_policy = drift_policy or DriftPolicy()

    base: dict[str, Any] = {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "asof": asof,
        "exitPolicy": {
            "stop_loss": exit_policy.stop_loss,
            "take_profit": exit_policy.take_profit,
            "target_base": exit_policy.target_base,
            "trail_stop_pct": exit_policy.trail_stop_pct,
            "trail_min_peak_ret": exit_policy.trail_min_peak_ret,
            "min_hold": exit_policy.min_hold,
            "max_hold_days": exit_policy.max_hold_days,
            "trail_min_held": exit_policy.trail_min_held,
        },
        "cooldownDays": cooldown_policy.cooldown_days,
        "driftBand": drift_policy.band,
        "disclaimer": (
            "持仓复核（研究口径）；退出/冷静期/偏差规则与回测同一实现；"
            "非投资建议；默认 SIMULATE；不冒充 live。"
        ),
    }

    rows_in = [r for r in (holdings or []) if isinstance(r, Mapping)]
    if not rows_in:
        return {
            **base,
            "ok": False,
            "failClosed": True,
            "reason": "holdings 为空：无持仓可复核",
            "rows": [],
            "counts": {"exit": 0, "trim": 0, "add": 0, "hold": 0, "pending": 0},
        }

    out_rows: list[dict[str, Any]] = []
    counts = {"exit": 0, "trim": 0, "add": 0, "hold": 0, "pending": 0}

    for raw in rows_in:
        code_raw = _pick(raw, _CODE_KEYS)
        code = "" if code_raw is None else str(code_raw).strip()
        entry = _f(_pick(raw, _ENTRY_KEYS))
        px = _f(_pick(raw, _PRICE_KEYS))
        held_val = _f(raw.get("held_days"))
        held_unknown = held_val is None
        held = int(held_val) if held_val is not None else 0

        item: dict[str, Any] = {
            "code": code,
            "entry_price": entry,
            "price": px,
            "held_days": held,
            "held_days_unknown": held_unknown,
            "asset_class": None,
            "action": "pending",
            "reason": None,
            "ret_pct": None,
            "deviation": None,
            "deferred": False,
            "in_cooldown": False,
            "note": None,
        }

        if not code or entry is None or entry <= 0:
            item["note"] = "缺 code / entry_price，无法复核"
            counts["pending"] += 1
            out_rows.append(item)
            continue
        if px is None or px <= 0:
            item["note"] = "缺当前参考收盘价，无法复核"
            counts["pending"] += 1
            out_rows.append(item)
            continue

        from .portfolio import asset_class  # local import: keep module import-light

        item["asset_class"] = asset_class(code)

        # --- cooldown (冷静期) ---
        le = raw.get("last_exit_idx")
        le_idx = int(le) if isinstance(le, (int, float)) and current_idx is not None else None
        if le_idx is not None:
            item["in_cooldown"] = cooldown_policy.blocks(
                last_exit_idx=le_idx, current_idx=int(current_idx)
            )

        # --- peak + exit (the shared call) ---
        peak = _f(raw.get("peak"))
        peak = entry if peak is None else peak
        peak = advance_peak(peak, px)
        target = _f(raw.get("target"))
        target = exit_policy.target_price(entry) if target is None else target

        decision = evaluate_exit(
            px=px,
            entry_price=entry,
            target=target,
            peak=peak,
            held_days=held,
            ma20=raw.get("ma20"),
            ma60=raw.get("ma60"),
            policy=exit_policy,
        )
        item["peak"] = peak
        item["target"] = target

        if decision is not None:
            item["action"] = "exit"
            item["reason"] = decision.reason
            item["ret_pct"] = round(decision.ret_pct, 4)
            if is_limit_down(code, raw.get("pct_chg")):
                item["deferred"] = True
                item["note"] = "跌停封板，卖单顺延至下一交易日（与回测同规则）"
        else:
            drift = evaluate_drift(
                weight=raw.get("weight"),
                target_weight=raw.get("target_weight"),
                policy=drift_policy,
            )
            item["action"] = drift.action
            item["deviation"] = None if drift.deviation is None else round(drift.deviation, 6)
            item["ret_pct"] = round((px / entry - 1.0) * 100.0, 4)

        if held_unknown and item["note"] is None:
            item["note"] = "持有天数未知（按 0 处理：仅保护性退出可触发）"

        counts[item["action"] if item["action"] in counts else "hold"] += 1
        out_rows.append(item)

    any_priced = any(r["action"] != "pending" for r in out_rows)
    return {
        **base,
        "ok": bool(any_priced),
        "failClosed": not any_priced,
        "reason": None if any_priced else "所有持仓缺当前价，无法复核",
        "holdingCount": len(out_rows),
        "rows": out_rows,
        "counts": counts,
    }


def format_review_markdown(review: Mapping[str, Any]) -> str:
    """Render a :func:`review_positions` payload as a compact markdown table."""
    rows = list(review.get("rows") or [])
    lines = ["# 持仓复核（SIMULATE · 非投资建议）", ""]
    counts = review.get("counts") or {}
    lines.append(
        "| 动作 | 数量 |\n|---|---|\n"
        + "\n".join(f"| {k} | {v} |" for k, v in counts.items())
    )
    lines.append("")
    lines.append("| 代码 | 类别 | 持有天数 | 收益% | 动作 | 原因 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            "| {code} | {cls} | {held} | {ret} | {act} | {reason} | {note} |".format(
                code=r.get("code") or "",
                cls=r.get("asset_class") or "",
                held=r.get("held_days"),
                ret="" if r.get("ret_pct") is None else f"{r['ret_pct']:+.2f}",
                act=r.get("action") or "",
                reason=r.get("reason") or "",
                note=r.get("note") or ("冷静期内" if r.get("in_cooldown") else ""),
            )
        )
    lines.append("")
    lines.append(f"> {review.get('disclaimer')}")
    return "\n".join(lines) + "\n"


__all__ = ["format_review_markdown", "review_positions"]
