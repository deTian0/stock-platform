"""③B 操作建议的「具体数量」换算层。

规则层（``rules.evaluate_exit`` / ``evaluate_drift``）是**与仓位无关**的：
它只回答「该不该动」，不回答「动多少股」。这是刻意的——同一套规则要同时服务回测，
而回测自带股本书。代价是 ③B 长期只输出 ``stop_loss(-15.1%)`` 这种**不可执行**的结论。

本模块是**呈现侧的换算步骤**：拿到复核裁决（``position_review.review_positions``）
和账本行（自带 ``qty`` / ``available_qty`` / ``price``），把它翻译成整手取整的委托。

数量只有两个来源，优先级从高到低：

1. ``exit`` 裁决 ⇒ 卖掉**全部可卖**股数（``available_qty``，缺失回退 ``qty``）。
   止损是全有全无的，规则里没有「半仓止损」这回事。
2. ``单票上限``（``cap_weight``）⇒ 若复核后仓位**仍**超过上限，按整手减到上限。
   这是唯一会产生「部分卖出」的地方，且**永不产生 add**。

不实现 ``add``：账本只有一个现金数字、没有组合层面的目标权重，
任何买入数量都只能是拍脑袋，宁可不给。

SIMULATE only. 非投资建议。
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

#: 单票权重上限。超上限触发 trim-to-cap（ADR 0081）。
DEFAULT_CAP_WEIGHT = 0.20

#: A 股 / 场内 ETF 的最小交易单位（1 手 = 100 股）。
DEFAULT_LOT = 100


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _code_of(row: Mapping[str, Any]) -> str:
    for k in ("code", "symbol", "ts_code"):
        if row.get(k) is not None:
            return str(row[k]).strip()
    return ""


def _floor_lot(qty: float, lot: int) -> int:
    if lot <= 1:
        return int(qty)
    return int(math.floor(qty / lot) * lot)


def _ceil_lot(qty: float, lot: int) -> int:
    if lot <= 1:
        return int(math.ceil(qty))
    return int(math.ceil(qty / lot) * lot)


def plan_orders(
    book: Sequence[Mapping[str, Any]],
    review: Mapping[str, Any],
    *,
    cap_weight: float | None = DEFAULT_CAP_WEIGHT,
    lot: int = DEFAULT_LOT,
    total_value: float | None = None,
) -> dict[str, Any]:
    """把复核裁决翻译成具体委托数量。

    ``book`` 是账本行（``rankings.enrich_holdings`` 之后），``review`` 是
    ``review_positions`` 的返回。``total_value`` 缺省时按账本市值合计
    （不含现金）——传总资产可以拿到更贴近账户的权重口径。

    每笔委托：``{code, action, reason, qty, price, amount, weightBefore,
    weightAfter, available, unsellable, capped}``；``qty == 0`` 表示不动。
    """
    rows = [r for r in (book or []) if isinstance(r, Mapping)]
    verdicts = {
        _code_of(r): r
        for r in ((review or {}).get("rows") or [])
        if isinstance(r, Mapping)
    }

    priced: list[tuple[Mapping[str, Any], float, int, int]] = []
    for row in rows:
        code = _code_of(row)
        px = _f(row.get("price"))
        qty = _f(row.get("qty"))
        if not code or px is None or px <= 0 or qty is None or qty <= 0:
            continue
        avail = _f(row.get("available_qty"))
        avail_i = int(qty) if avail is None else max(int(avail), 0)
        priced.append((row, px, int(qty), avail_i))

    total = _f(total_value)
    if total is None or total <= 0:
        total = sum(px * qty for _, px, qty, _ in priced)
    total = total or 0.0
    cap = _f(cap_weight)
    cap_value = cap * total if (cap is not None and cap > 0 and total > 0) else None

    orders: list[dict[str, Any]] = []
    for row, px, qty, avail in priced:
        code = _code_of(row)
        verdict = verdicts.get(code) or {}
        action = str(verdict.get("action") or "hold")
        reason = verdict.get("reason")
        mv = px * qty
        weight_before = (mv / total) if total > 0 else None

        sell_qty = 0
        order_action = "none"
        capped = False

        if action == "exit":
            sell_qty = _floor_lot(avail, lot)
            order_action = "exit"
            if verdict.get("deferred"):
                order_action = "exit_deferred"
        elif cap_value is not None and mv > cap_value:
            excess = mv - cap_value
            sell_raw = excess / px
            sell_qty = min(_ceil_lot(sell_raw, lot), _floor_lot(avail, lot))
            order_action = "trim" if sell_qty > 0 else "none"
            capped = True
            reason = reason or (
                f"单票权重 {weight_before * 100:.2f}% 超过上限 {cap * 100:.0f}%（缩到上限）"
                if weight_before is not None
                else "超过单票权重上限"
            )

        remaining = qty - sell_qty
        amount = sell_qty * px
        orders.append(
            {
                "code": code,
                "name": row.get("name"),
                "action": order_action,
                "ruleAction": action,
                "reason": reason,
                "qty": sell_qty,
                "heldQty": qty,
                "available": avail,
                "unsellable": qty - avail,
                "price": px,
                "amount": round(amount, 2),
                "weightBefore": None if weight_before is None else round(weight_before, 6),
                "weightAfter": (
                    None
                    if not total
                    else round((remaining * px) / total, 6)
                ),
                "remainingQty": remaining,
                "capped": capped,
                "assetClass": verdict.get("asset_class") or row.get("asset_class"),
            }
        )

    actionable = [o for o in orders if o["qty"] > 0]
    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "ok": True,
        "capWeight": cap,
        "lot": lot,
        "totalValue": round(total, 2),
        "orders": orders,
        "counts": {
            "sell": len(actionable),
            "exit": sum(1 for o in actionable if o["action"].startswith("exit")),
            "trim": sum(1 for o in actionable if o["action"] == "trim"),
            "none": len(orders) - len(actionable),
        },
        "totalAmount": round(sum(o["amount"] for o in actionable), 2),
        "disclaimer": (
            "数量按整手取整；exit=b 全部可卖，trim=减到单票上限；"
            "不产生加仓建议。SIMULATE，非投资建议。"
        ),
    }


__all__ = ["DEFAULT_CAP_WEIGHT", "DEFAULT_LOT", "plan_orders"]
