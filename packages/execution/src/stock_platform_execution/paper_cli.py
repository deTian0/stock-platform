"""CLI ``stock-platform-paper`` — minimal SIMULATE paper loop (no live switch)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .lifecycle import StrategyLifecycle
from .paper import PaperLedger
from .errors import DraftBlocked, IdempotentReplay

# Session file keeps draft/accepted ids across subcommands in one agent turn.
DEFAULT_STATE = Path("local") / "paper_session.json"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"lifecycle": {}, "drafts": {}, "accepted": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"lifecycle": {}, "drafts": {}, "accepted": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_now(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo

        dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return dt


def _hydrate_ledger(state: dict[str, Any]) -> PaperLedger:
    ledger = PaperLedger()
    for draft_id, draft in (state.get("drafts") or {}).items():
        ledger._drafts[str(draft_id)] = dict(draft)  # noqa: SLF001 — CLI session restore
    for draft_id, accepted in (state.get("accepted") or {}).items():
        ledger._accepted[str(draft_id)] = dict(accepted)  # noqa: SLF001
    return ledger


def _persist_ledger(state: dict[str, Any], ledger: PaperLedger) -> None:
    state["drafts"] = {k: dict(v) for k, v in ledger._drafts.items()}  # noqa: SLF001
    state["accepted"] = {k: dict(v) for k, v in ledger._accepted.items()}  # noqa: SLF001


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.state)
    ledger = _hydrate_ledger(state)
    life = StrategyLifecycle()
    snap = state.get("lifecycle") or {}
    if snap.get("active"):
        life.active = dict(snap["active"])
    out = {
        **ledger.status(),
        "lifecycle": life.snapshot(),
        "statePath": str(args.state),
        "liveTradingEnabled": False,
    }
    return out


def cmd_ensure_default(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.state)
    life = StrategyLifecycle()
    snap = state.get("lifecycle") or {}
    if snap.get("active"):
        life.active = dict(snap["active"])
        life.validated = dict(snap["validated"]) if snap.get("validated") else None
        life.draft = dict(snap["draft"]) if snap.get("draft") else None
    result = life.ensure_default_simulate_active(execution_safety_passed=True)
    state["lifecycle"] = life.snapshot()
    _save_state(args.state, state)
    return {
        **result,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "statePath": str(args.state),
    }


def cmd_draft(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.state)
    life_snap = state.get("lifecycle") or {}
    strategy_hash = args.strategy_hash or (life_snap.get("active") or {}).get("strategyHash") or "cli"
    ledger = _hydrate_ledger(state)
    orders = [{"symbol": args.symbol, "side": args.side, "qty": args.qty}]
    draft = ledger.build_draft(
        strategy_hash=str(strategy_hash),
        signal_trade_date=str(args.signal_date),
        orders=orders,
        now=_parse_now(args.now),
        decision_only=bool(args.decision_only),
        market=str(args.market),
    )
    _persist_ledger(state, ledger)
    _save_state(args.state, state)
    return draft


def cmd_execute(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.state)
    ledger = _hydrate_ledger(state)
    try:
        result = ledger.execute_draft(str(args.draft_id), now=_parse_now(args.now))
    except IdempotentReplay as exc:
        result = {
            "accepted": True,
            "idempotentReplay": True,
            "draftId": exc.draft_id,
            "executionId": exc.execution_id,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }
    except DraftBlocked as exc:
        raise SystemExit(f"draft blocked: {exc}") from exc
    _persist_ledger(state, ledger)
    _save_state(args.state, state)
    return result


def cmd_demo(args: argparse.Namespace) -> dict[str, Any]:
    """One-shot: ensure-default → draft → execute (clock via --now)."""
    ensure = cmd_ensure_default(args)
    args.strategy_hash = ensure.get("strategyHash")
    if not args.signal_date:
        args.signal_date = "2026-09-04"
    if not args.now:
        args.now = "2026-09-07T09:40:00+08:00"
    if not args.symbol:
        args.symbol = "510300"
    draft = cmd_draft(args)
    args.draft_id = draft["draftId"]
    try:
        executed = cmd_execute(args)
    except SystemExit:
        executed = {"accepted": False, "draft": draft}
    return {
        "ensure": ensure,
        "draft": draft,
        "execute": executed,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="stock-platform-paper",
        description="纸面 SIMULATE 最小闭环（无 live 开关）。",
    )
    p.add_argument("--state", type=Path, default=DEFAULT_STATE, help="会话状态 JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="环境与会话摘要")
    sub.add_parser("ensure-default", help="幂等激活默认 SIMULATE 策略")

    d = sub.add_parser("draft", help="建纸面草稿")
    d.add_argument("--signal-date", required=True, help="信号日 YYYY-MM-DD")
    d.add_argument("--symbol", default="510300")
    d.add_argument("--side", default="buy")
    d.add_argument("--qty", type=int, default=100)
    d.add_argument("--strategy-hash", default=None)
    d.add_argument("--now", default=None, help="注入时钟 ISO8601（测试/agent 用）")
    d.add_argument("--decision-only", action="store_true")
    d.add_argument("--market", default="CN")

    e = sub.add_parser("execute", help="执行已eligible草稿")
    e.add_argument("--draft-id", required=True)
    e.add_argument("--now", default=None)

    demo = sub.add_parser("demo", help="ensure→draft→execute 一键冒烟")
    demo.add_argument("--signal-date", default="2026-09-04")
    demo.add_argument("--symbol", default="510300")
    demo.add_argument("--side", default="buy")
    demo.add_argument("--qty", type=int, default=100)
    demo.add_argument("--now", default="2026-09-07T09:40:00+08:00")
    demo.add_argument("--market", default="CN")
    demo.add_argument("--decision-only", action="store_true")
    demo.add_argument("--strategy-hash", default=None)

    args = p.parse_args(argv)
    handlers = {
        "status": cmd_status,
        "ensure-default": cmd_ensure_default,
        "draft": cmd_draft,
        "execute": cmd_execute,
        "demo": cmd_demo,
    }
    out = handlers[args.cmd](args)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(
        f"paper cmd={args.cmd} liveTradingEnabled=false",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
