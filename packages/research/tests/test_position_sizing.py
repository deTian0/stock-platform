"""持仓数量折算（ADR 0081）—— ③B 必须给出可执行股数。

覆盖三条不变量：

1. ``exit`` 裁决 ⇒ 卖出**全部可卖**股数，且不超过 ``available_qty``；
2. 超单票上限 ⇒ 按整手减到上限，剩余权重必须真的落到上限以内；
3. **永不产生 add** —— 账本缺少组合目标权重，任何买入量都是编的。
"""

from __future__ import annotations

from stock_platform_research.position_sizing import (
    DEFAULT_CAP_WEIGHT,
    DEFAULT_LOT,
    plan_orders,
)


def _row(code, qty, price, entry=10.0, avail=None, name=None):
    row = {
        "code": code,
        "name": name or code,
        "qty": qty,
        "entry_price": entry,
        "price": price,
        "asset_class": "stock",
    }
    if avail is not None:
        row["available_qty"] = avail
    return row


def _review(*rows):
    return {"rows": list(rows)}


def test_exit_sells_every_sellable_share():
    book = [_row("000533", 900, 8.67, entry=10.21, avail=900)]
    review = _review(
        {"code": "000533", "action": "exit", "reason": "stop_loss(-15.1%)", "ret_pct": -15.08}
    )
    plan = plan_orders(book, review)
    order = plan["orders"][0]
    assert order["action"] == "exit"
    assert order["qty"] == 900
    assert order["amount"] == 7803.0
    assert order["remainingQty"] == 0
    assert order["reason"] == "stop_loss(-15.1%)"


def test_exit_never_exceeds_available_shares():
    # 今日买入 100 股（T+1 冻结）⇒ 只能卖掉可用的那一部分。
    book = [_row("000553", 500, 4.91, avail=400)]
    review = _review({"code": "000553", "action": "exit", "reason": "stop_loss(-9.0%)"})
    order = plan_orders(book, review)["orders"][0]
    assert order["qty"] == 400
    assert order["unsellable"] == 100
    assert order["remainingQty"] == 100


def test_over_cap_trim_lands_inside_cap_in_whole_lots():
    # 市值 7803 / 总市值 10503.6 = 74.3%，上限 20% ⇒ 必须减到 20% 以内。
    book = [_row("000533", 900, 8.67, entry=10.21, avail=900)]
    review = _review({"code": "000533", "action": "hold", "ret_pct": -15.08})
    plan = plan_orders(book, review)
    order = plan["orders"][0]
    assert order["action"] == "trim"
    assert order["capped"] is True
    assert order["qty"] % DEFAULT_LOT == 0
    assert order["weightAfter"] <= DEFAULT_CAP_WEIGHT
    assert order["reason"].startswith("单票权重")


def test_under_cap_hold_produces_no_order():
    book = [
        _row("600963", 500, 3.38, avail=500),
        _row("000553", 100, 4.91, avail=0),
    ]
    review = _review(
        {"code": "600963", "action": "hold", "ret_pct": -1.52},
        {"code": "000553", "action": "hold", "ret_pct": -0.20},
    )
    # 用真实账户总资产做分母，否则只有两只票的账本会把它们的权重算到 77%。
    plan = plan_orders(book, review, total_value=10513.53)
    assert all(o["qty"] == 0 for o in plan["orders"])
    assert plan["counts"]["sell"] == 0
    assert plan["totalAmount"] == 0.0


def test_no_add_is_ever_produced():
    # 权重远低于上限也绝不补仓（没有目标权重，买入量无处推导）。
    book = [_row("000553", 100, 4.91, avail=0)]
    review = _review({"code": "000553", "action": "hold", "ret_pct": -0.2})
    plan = plan_orders(book, review)
    assert all(o["action"] != "add" for o in plan["orders"])
    assert plan["counts"]["trim"] == 0


def test_exit_beats_cap_trim():
    # 同时满足 exit 与超上限时，按 exit 全清，而不是只 trim 到上限。
    book = [_row("000533", 900, 8.67, entry=10.21, avail=900)]
    review = _review({"code": "000533", "action": "exit", "reason": "stop_loss(-15.1%)"})
    order = plan_orders(book, review)["orders"][0]
    assert order["action"] == "exit"
    assert order["remainingQty"] == 0


def test_rows_without_price_are_skipped_not_guessed():
    book = [{"code": "588080", "qty": 400, "price": None}]
    plan = plan_orders(book, _review({"code": "588080", "action": "hold"}))
    assert plan["orders"] == []


def test_total_value_override_changes_weights():
    book = [_row("000533", 900, 8.67, avail=900)]
    review = _review({"code": "000533", "action": "hold"})
    small = plan_orders(book, review, total_value=10503.6)["orders"][0]
    big = plan_orders(book, review, total_value=21007.2)["orders"][0]
    assert small["weightBefore"] > big["weightBefore"]
    assert small["qty"] > big["qty"]
