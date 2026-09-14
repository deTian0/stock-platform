"""Broker port: PaperBroker (default) vs ExternalSimBroker (opt-in)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from .contracts import AccountSnapshot, Fill, OrderIntent, Position
from .errors import BrokerConfigError, DraftBlocked
from .paper import PaperLedger


@runtime_checkable
class BrokerPort(Protocol):
    """Unified SIMULATE broker surface used by workbench / recommend paths."""

    name: str

    def build_draft(
        self,
        *,
        strategy_hash: str,
        signal_trade_date: str,
        orders: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
        decision_only: bool = False,
        now: datetime | None = None,
        observed_raw_dates: list[str] | None = None,
        market: str = "CN",
    ) -> dict[str, Any]: ...

    def execute_draft(
        self,
        draft_id: str,
        *,
        profile: dict[str, Any] | None = None,
        now: datetime | None = None,
        max_draft_age_seconds: int = 600,
        market: str = "CN",
    ) -> dict[str, Any]: ...

    def status(self) -> dict[str, Any]: ...

    def get_positions(self) -> list[Position]: ...

    def get_orders(self) -> list[dict[str, Any]]: ...

    def get_account(self) -> AccountSnapshot: ...

    def get_fills(self) -> list[Fill]: ...


@runtime_checkable
class ExternalSimBroker(BrokerPort, Protocol):
    """External simulation venue (still SIMULATE; never live brokerage)."""

    venue: str


class PaperBroker:
    """Default broker: in-memory PaperLedger. No external network."""

    name = "paper"
    venue = "paper_ledger"

    def __init__(self, ledger: PaperLedger | None = None) -> None:
        self.ledger = ledger or PaperLedger()
        self._fills: list[Fill] = []
        self._positions: dict[str, Position] = {}
        self._cash: float = 1_000_000.0
        self._last_errors: list[str] = []

    def build_draft(
        self,
        *,
        strategy_hash: str,
        signal_trade_date: str,
        orders: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
        decision_only: bool = False,
        now: datetime | None = None,
        observed_raw_dates: list[str] | None = None,
        market: str = "CN",
    ) -> dict[str, Any]:
        draft = self.ledger.build_draft(
            strategy_hash=strategy_hash,
            signal_trade_date=signal_trade_date,
            orders=orders,
            profile=profile,
            decision_only=decision_only,
            now=now,
            observed_raw_dates=observed_raw_dates,
            market=market,
        )
        draft["broker"] = self.name
        return draft

    def execute_draft(
        self,
        draft_id: str,
        *,
        profile: dict[str, Any] | None = None,
        now: datetime | None = None,
        max_draft_age_seconds: int = 600,
        market: str = "CN",
    ) -> dict[str, Any]:
        result = self.ledger.execute_draft(
            draft_id,
            profile=profile,
            now=now,
            max_draft_age_seconds=max_draft_age_seconds,
            market=market,
        )
        self._apply_fills(result)
        result["broker"] = self.name
        return result

    def _apply_fills(self, result: dict[str, Any]) -> None:
        execution_id = str(result["executionId"])
        draft_id = str(result["draftId"])
        accepted_at = str(result.get("acceptedAt") or "")
        for i, raw in enumerate(result.get("orders") or []):
            intent = OrderIntent.from_dict(raw)
            px = float(raw.get("price") or raw.get("limit_price") or 0.0)
            fill = Fill(
                fill_id=f"{execution_id}:{i}",
                order_id=execution_id,
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                price=px,
                filled_at=accepted_at,
                draft_id=draft_id,
            )
            self._fills.append(fill)
            signed = intent.qty if intent.side == "buy" else -intent.qty
            prev = self._positions.get(intent.symbol)
            new_qty = (prev.qty if prev else 0.0) + signed
            if abs(new_qty) < 1e-12:
                self._positions.pop(intent.symbol, None)
            else:
                avg = px if not prev or prev.qty == 0 else prev.avg_price
                self._positions[intent.symbol] = Position(
                    symbol=intent.symbol, qty=new_qty, avg_price=avg
                )
            self._cash -= signed * px

    def status(self) -> dict[str, Any]:
        base = self.ledger.status()
        return {
            **base,
            "broker": self.name,
            "venue": self.venue,
            "lastErrors": list(self._last_errors),
        }

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_orders(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self.ledger._accepted.values()]  # noqa: SLF001

    def get_account(self) -> AccountSnapshot:
        equity = self._cash + sum(p.qty * p.avg_price for p in self._positions.values())
        return AccountSnapshot(
            cash=self._cash,
            equity=equity,
            account_id="paper",
            environment="SIMULATE",
            live_trading_enabled=False,
        )

    def get_fills(self) -> list[Fill]:
        return list(self._fills)


def broker_from_env(name: str | None = None) -> str:
    raw = (name if name is not None else os.environ.get("STOCK_PLATFORM_BROKER", "paper")) or "paper"
    key = str(raw).strip().lower()
    if key not in {"paper", "ths_sim"}:
        raise BrokerConfigError(
            f"STOCK_PLATFORM_BROKER must be 'paper' or 'ths_sim', got {raw!r}"
        )
    return key


def resolve_broker(name: str | None = None, **kwargs: Any) -> BrokerPort:
    """Resolve SIMULATE broker. Default paper. ths_sim is opt-in only."""
    key = broker_from_env(name)
    if key == "paper":
        ledger = kwargs.get("ledger")
        return PaperBroker(ledger=ledger) if isinstance(ledger, PaperLedger) else PaperBroker()
    if key == "ths_sim":
        # Imported lazily so paper-only installs never load THS adapter.
        try:
            from .ths_sim import ThsSimBroker
        except ImportError as exc:  # pragma: no cover - missing module before M36
            raise BrokerConfigError(
                "ths_sim broker is not installed yet; use STOCK_PLATFORM_BROKER=paper "
                "or upgrade to a release that includes ThsSimBroker"
            ) from exc
        return ThsSimBroker.from_env(**kwargs)
    raise BrokerConfigError(f"unsupported broker {key!r}")


def orders_as_intents(orders: list[dict[str, Any]]) -> list[OrderIntent]:
    return [OrderIntent.from_dict(o) for o in orders]


def require_executable_draft(draft: dict[str, Any]) -> None:
    if draft.get("decisionOnly") or not draft.get("executionEligible"):
        raise DraftBlocked(
            f"draft not executable: decisionOnly={draft.get('decisionOnly')} "
            f"eligible={draft.get('executionEligible')} reasons={draft.get('blockedReasons')}"
        )
    if not draft.get("orders"):
        raise DraftBlocked("refusing to submit empty order list")
