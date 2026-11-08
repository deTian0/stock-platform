"""CLI ``stock-platform-paper`` — 本仓模拟舱（PaperBroker SIMULATE，无 live 开关）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .errors import DraftBlocked, IdempotentReplay
from .lifecycle import StrategyLifecycle
from .paper_cabin import (
    DEFAULT_STATE,
    hydrate_broker,
    load_state,
    parse_now,
    persist_broker,
    resolve_fill_price,
    save_state,
)


def _account_payload(broker: Any) -> dict[str, Any]:
    return broker.get_account().to_dict()


def _positions_payload(broker: Any) -> list[dict[str, Any]]:
    return [p.to_dict() for p in broker.get_positions()]


def _fills_payload(broker: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    fills = [f.to_dict() for f in broker.get_fills()]
    if limit is not None and limit >= 0:
        return fills[-limit:]
    return fills


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    broker = hydrate_broker(state)
    life = StrategyLifecycle()
    snap = state.get("lifecycle") or {}
    if snap.get("active"):
        life.active = dict(snap["active"])
    out = {
        **broker.status(),
        "lifecycle": life.snapshot(),
        "account": _account_payload(broker),
        "positions": _positions_payload(broker),
        "fillCount": len(broker.get_fills()),
        "statePath": str(args.state),
        "cabin": "paper",
        "liveTradingEnabled": False,
        "hint": "本仓模拟舱=PaperBroker；ths_sim mock 仅演示端口，见 docs/ops/paper-cabin.md",
    }
    return out


def cmd_ensure_default(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    life = StrategyLifecycle()
    snap = state.get("lifecycle") or {}
    if snap.get("active"):
        life.active = dict(snap["active"])
        life.validated = dict(snap["validated"]) if snap.get("validated") else None
        life.draft = dict(snap["draft"]) if snap.get("draft") else None
    result = life.ensure_default_simulate_active(execution_safety_passed=True)
    state["lifecycle"] = life.snapshot()
    save_state(args.state, state)
    return {
        **result,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "statePath": str(args.state),
    }


def cmd_draft(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    life_snap = state.get("lifecycle") or {}
    strategy_hash = args.strategy_hash or (life_snap.get("active") or {}).get("strategyHash") or "cli"
    broker = hydrate_broker(state)
    price = float(args.price) if getattr(args, "price", None) is not None else None
    order: dict[str, Any] = {"symbol": args.symbol, "side": args.side, "qty": args.qty}
    if price is not None:
        order["price"] = price
    draft = broker.build_draft(
        strategy_hash=str(strategy_hash),
        signal_trade_date=str(args.signal_date),
        orders=[order],
        now=parse_now(args.now),
        decision_only=bool(args.decision_only),
        market=str(args.market),
    )
    persist_broker(state, broker)
    save_state(args.state, state)
    return draft


def cmd_execute(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    broker = hydrate_broker(state)
    try:
        result = broker.execute_draft(str(args.draft_id), now=parse_now(args.now))
    except IdempotentReplay as exc:
        result = {
            "accepted": True,
            "idempotentReplay": True,
            "draftId": exc.draft_id,
            "executionId": exc.execution_id,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "broker": "paper",
        }
    except DraftBlocked as exc:
        raise SystemExit(f"draft blocked: {exc}") from exc
    persist_broker(state, broker)
    save_state(args.state, state)
    return {
        **result,
        "account": _account_payload(broker),
        "positions": _positions_payload(broker),
    }


def _one_shot_trade(args: argparse.Namespace, *, side: str) -> dict[str, Any]:
    state = load_state(args.state)
    life_snap = state.get("lifecycle") or {}
    if not (life_snap.get("active") or {}).get("strategyHash"):
        ensure = cmd_ensure_default(args)
        state = load_state(args.state)
        strategy_hash = ensure.get("strategyHash") or "cli"
    else:
        strategy_hash = args.strategy_hash or (life_snap.get("active") or {}).get("strategyHash") or "cli"

    broker = hydrate_broker(state)
    qty = int(args.qty)
    symbol = str(args.symbol)

    if side == "sell":
        pos_map = {p.symbol: p for p in broker.get_positions()}
        pos = pos_map.get(symbol)
        if pos is None or pos.qty <= 0:
            raise SystemExit(f"无持仓可平：{symbol}")
        if getattr(args, "all", False):
            qty = int(pos.qty)
        if qty <= 0:
            raise SystemExit("qty must be > 0")
        if qty > pos.qty + 1e-9:
            raise SystemExit(f"平仓数量 {qty} 超过持仓 {pos.qty}")

    asof = str(args.signal_date)
    if (
        side == "sell"
        and getattr(args, "use_avg", False)
        and args.price is None
        and args.db is None
    ):
        pos_map = {p.symbol: p for p in broker.get_positions()}
        pos = pos_map[symbol]
        if pos.avg_price <= 0:
            raise SystemExit("持仓均价无效，无法 --use-avg；请传 --price 或 --db")
        px, source = float(pos.avg_price), "position:avg_price"
    else:
        try:
            px, source = resolve_fill_price(
                symbol,
                asof=asof,
                price=float(args.price) if args.price is not None else None,
                db=args.db,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    draft = broker.build_draft(
        strategy_hash=str(strategy_hash),
        signal_trade_date=asof,
        orders=[{"symbol": symbol, "side": side, "qty": qty, "price": px}],
        now=parse_now(args.now),
        decision_only=False,
        market=str(args.market),
    )
    try:
        executed = broker.execute_draft(draft["draftId"], now=parse_now(args.now))
    except DraftBlocked as exc:
        persist_broker(state, broker)
        save_state(args.state, state)
        raise SystemExit(f"draft blocked: {exc}") from exc
    except IdempotentReplay as exc:
        executed = {
            "accepted": True,
            "idempotentReplay": True,
            "draftId": exc.draft_id,
            "executionId": exc.execution_id,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "broker": "paper",
        }

    persist_broker(state, broker)
    save_state(args.state, state)
    return {
        "side": side,
        "symbol": symbol,
        "qty": qty,
        "price": px,
        "priceSource": source,
        "draft": draft,
        "execute": executed,
        "account": _account_payload(broker),
        "positions": _positions_payload(broker),
        "fills": _fills_payload(broker, limit=5),
        "statePath": str(args.state),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "cabin": "paper",
        "broker": "paper",
    }


def cmd_buy(args: argparse.Namespace) -> dict[str, Any]:
    return _one_shot_trade(args, side="buy")


def cmd_sell(args: argparse.Namespace) -> dict[str, Any]:
    return _one_shot_trade(args, side="sell")


def cmd_positions(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    broker = hydrate_broker(state)
    return {
        "positions": _positions_payload(broker),
        "statePath": str(args.state),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "cabin": "paper",
    }


def cmd_account(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    broker = hydrate_broker(state)
    return {
        "account": _account_payload(broker),
        "statePath": str(args.state),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "cabin": "paper",
    }


def cmd_fills(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    broker = hydrate_broker(state)
    return {
        "fills": _fills_payload(broker, limit=int(args.limit)),
        "fillCount": len(broker.get_fills()),
        "statePath": str(args.state),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "cabin": "paper",
    }


def cmd_demo(args: argparse.Namespace) -> dict[str, Any]:
    """One-shot: ensure-default → buy → positions/account (clock via --now)."""
    if not args.signal_date:
        args.signal_date = "2026-09-04"
    if not args.now:
        args.now = "2026-09-07T09:40:00+08:00"
    if not args.symbol:
        args.symbol = "510300"
    if args.price is None:
        args.price = 4.5
    ensure = cmd_ensure_default(args)
    args.strategy_hash = ensure.get("strategyHash")
    try:
        trade = cmd_buy(args)
    except SystemExit as exc:
        return {
            "ensure": ensure,
            "error": str(exc),
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }
    return {
        "ensure": ensure,
        "buy": trade,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "cabin": "paper",
        "statePath": str(args.state),
    }


def _add_trade_args(p: argparse.ArgumentParser, *, sell: bool = False) -> None:
    p.add_argument("--symbol", required=True, help="证券代码，如 600519 / 510300")
    if sell:
        p.add_argument("--qty", type=int, default=0, help="平仓数量；与 --all 二选一")
        p.add_argument("--all", action="store_true", help="平掉该标的全部持仓")
    else:
        p.add_argument("--qty", type=int, required=True, help="买入数量")
    p.add_argument("--price", type=float, default=None, help="成交价（离线演示必填，除非 --db）")
    p.add_argument("--db", type=Path, default=None, help="只读 market.db（取 asof 收盘价）")
    p.add_argument("--signal-date", required=True, help="信号日 YYYY-MM-DD（闸门用）")
    p.add_argument("--now", required=True, help="注入时钟 ISO8601（须落在执行窗口）")
    p.add_argument("--strategy-hash", default=None)
    p.add_argument("--market", default="CN")
    if sell:
        p.add_argument(
            "--use-avg",
            action="store_true",
            help="无 --price/--db 时用持仓均价平仓（标注 position:avg_price）",
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="stock-platform-paper",
        description="本仓模拟舱：PaperBroker 纸面买卖（SIMULATE，无 live 开关）。",
    )
    p.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE,
        help="模拟舱状态 JSON（默认 local/paper_cabin/state.json）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="环境与会话摘要（含账户/持仓）")
    sub.add_parser("ensure-default", help="幂等激活默认 SIMULATE 策略")

    d = sub.add_parser("draft", help="建纸面草稿")
    d.add_argument("--signal-date", required=True, help="信号日 YYYY-MM-DD")
    d.add_argument("--symbol", default="510300")
    d.add_argument("--side", default="buy")
    d.add_argument("--qty", type=int, default=100)
    d.add_argument("--price", type=float, default=None)
    d.add_argument("--strategy-hash", default=None)
    d.add_argument("--now", default=None, help="注入时钟 ISO8601（测试/agent 用）")
    d.add_argument("--decision-only", action="store_true")
    d.add_argument("--market", default="CN")

    e = sub.add_parser("execute", help="执行已 eligible 草稿")
    e.add_argument("--draft-id", required=True)
    e.add_argument("--now", default=None)

    buy = sub.add_parser("buy", aliases=["open"], help="一键开仓（draft→execute→落盘）")
    _add_trade_args(buy, sell=False)

    sell = sub.add_parser("sell", aliases=["close"], help="一键平仓（draft→execute→落盘）")
    _add_trade_args(sell, sell=True)

    sub.add_parser("positions", help="查持仓")
    sub.add_parser("account", help="查账户资金")
    fills = sub.add_parser("fills", help="最近成交")
    fills.add_argument("--limit", type=int, default=20, help="返回最近 N 笔（默认 20）")

    demo = sub.add_parser("demo", help="ensure→buy 一键冒烟（默认价 4.5）")
    demo.add_argument("--signal-date", default="2026-09-04")
    demo.add_argument("--symbol", default="510300")
    demo.add_argument("--qty", type=int, default=100)
    demo.add_argument("--price", type=float, default=4.5)
    demo.add_argument("--db", type=Path, default=None)
    demo.add_argument("--now", default="2026-09-07T09:40:00+08:00")
    demo.add_argument("--market", default="CN")
    demo.add_argument("--strategy-hash", default=None)

    args = p.parse_args(argv)
    if args.cmd in {"sell", "close"} and not args.all and int(args.qty or 0) <= 0:
        raise SystemExit("sell/close 须指定 --qty > 0 或 --all")

    handlers = {
        "status": cmd_status,
        "ensure-default": cmd_ensure_default,
        "draft": cmd_draft,
        "execute": cmd_execute,
        "buy": cmd_buy,
        "open": cmd_buy,
        "sell": cmd_sell,
        "close": cmd_sell,
        "positions": cmd_positions,
        "account": cmd_account,
        "fills": cmd_fills,
        "demo": cmd_demo,
    }
    out = handlers[args.cmd](args)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(
        f"paper-cabin cmd={args.cmd} liveTradingEnabled=false",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
