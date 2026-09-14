"""ThsSimBroker — Tonghuashun SIMULATE adapter (mock default; HTTP experimental).

Research (2026-09): no stable public retail THS paper-trading OpenAPI.
Official paths (iFinD / SuperMind) are not embeddable HTTP counter APIs.
This module ships:
  1. Full ExternalSimBroker interface
  2. Injectable transport + MockThsTransport for CI (zero public net)
  3. ExperimentalThsHttpTransport — fail-closed without STOCK_PLATFORM_THS_*;
     not production-ready (pending real wire-up)

Never enables liveTradingEnabled. Default broker remains paper.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .contracts import AccountSnapshot, Fill, OrderIntent, Position
from .errors import BrokerConfigError, BrokerTransportError, DraftBlocked, IdempotentReplay
from .paper import PaperLedger


JsonGet = Callable[..., dict[str, Any]]


class ThsTransport(Protocol):
    """Injectable HTTP / mock transport for THS sim endpoints."""

    def authenticate(self) -> dict[str, Any]: ...

    def place_orders(self, orders: list[dict[str, Any]], *, draft_id: str) -> dict[str, Any]: ...

    def list_positions(self) -> list[dict[str, Any]]: ...

    def list_orders(self) -> list[dict[str, Any]]: ...

    def account(self) -> dict[str, Any]: ...

    def poll_fills(self, *, since_execution_id: str | None = None) -> list[dict[str, Any]]: ...


class MockThsTransport:
    """In-memory THS sim venue for CI / local E2E (no network)."""

    def __init__(self, *, cash: float = 1_000_000.0, fixture_dir: Path | None = None) -> None:
        self.cash = cash
        self.positions: dict[str, dict[str, Any]] = {}
        self.orders: list[dict[str, Any]] = []
        self.fills: list[dict[str, Any]] = []
        self._authed = False
        self._fixture_dir = fixture_dir
        if fixture_dir and (fixture_dir / "account.json").is_file():
            raw = json.loads((fixture_dir / "account.json").read_text(encoding="utf-8"))
            self.cash = float(raw.get("cash", cash))

    def authenticate(self) -> dict[str, Any]:
        self._authed = True
        return {"ok": True, "mode": "mock", "accountId": "ths_mock"}

    def _require_auth(self) -> None:
        if not self._authed:
            raise BrokerTransportError("THS mock transport not authenticated")

    def place_orders(self, orders: list[dict[str, Any]], *, draft_id: str) -> dict[str, Any]:
        self._require_auth()
        execution_id = str(uuid.uuid4())
        placed: list[dict[str, Any]] = []
        for i, raw in enumerate(orders):
            intent = OrderIntent.from_dict(raw)
            px = float(raw.get("price") or raw.get("limit_price") or 10.0)
            order_id = f"{execution_id}:{i}"
            rec = {
                "orderId": order_id,
                "draftId": draft_id,
                "executionId": execution_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": intent.qty,
                "price": px,
                "status": "filled",
            }
            placed.append(rec)
            self.orders.append(rec)
            fill = {
                "fillId": f"fill-{order_id}",
                "orderId": order_id,
                "executionId": execution_id,
                "draftId": draft_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": intent.qty,
                "price": px,
                "filledAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            self.fills.append(fill)
            signed = intent.qty if intent.side == "buy" else -intent.qty
            prev = self.positions.get(intent.symbol) or {"symbol": intent.symbol, "qty": 0.0, "avg_price": 0.0}
            new_qty = float(prev["qty"]) + signed
            if abs(new_qty) < 1e-12:
                self.positions.pop(intent.symbol, None)
            else:
                self.positions[intent.symbol] = {
                    "symbol": intent.symbol,
                    "qty": new_qty,
                    "avg_price": px,
                }
            self.cash -= signed * px
        return {
            "executionId": execution_id,
            "draftId": draft_id,
            "accepted": True,
            "orders": placed,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "venue": "ths_mock",
        }

    def list_positions(self) -> list[dict[str, Any]]:
        self._require_auth()
        return list(self.positions.values())

    def list_orders(self) -> list[dict[str, Any]]:
        self._require_auth()
        return list(self.orders)

    def account(self) -> dict[str, Any]:
        self._require_auth()
        equity = self.cash + sum(
            float(p["qty"]) * float(p.get("avg_price") or 0) for p in self.positions.values()
        )
        return {
            "cash": self.cash,
            "equity": equity,
            "currency": "CNY",
            "accountId": "ths_mock",
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }

    def poll_fills(self, *, since_execution_id: str | None = None) -> list[dict[str, Any]]:
        self._require_auth()
        if not since_execution_id:
            return list(self.fills)
        out: list[dict[str, Any]] = []
        seen = False
        for f in self.fills:
            if f.get("executionId") == since_execution_id:
                seen = True
                continue
            if seen:
                out.append(f)
        return out if seen else [f for f in self.fills if f.get("executionId") == since_execution_id]


class ExperimentalThsHttpTransport:
    """Opt-in HTTP stub — fail-closed without creds; NOT production-ready.

    Real THS retail sim OpenAPI is unavailable/unstable. This transport only
    documents the extension point and refuses to invent fake endpoints.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        account: str | None = None,
        get_json: JsonGet | None = None,
    ) -> None:
        if not base_url or not token:
            raise BrokerConfigError(
                "experimental THS HTTP requires STOCK_PLATFORM_THS_BASE_URL and "
                "STOCK_PLATFORM_THS_TOKEN (fail-closed)"
            )
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.account = account or ""
        self._get_json = get_json
        self._authed = False
        self._last_error: str | None = None

    def authenticate(self) -> dict[str, Any]:
        # Deliberately no default public endpoint — inject get_json in tests only.
        if self._get_json is None:
            raise BrokerTransportError(
                "experimental THS HTTP has no stable public wire-up; "
                "inject get_json for tests or keep STOCK_PLATFORM_THS_MODE=mock "
                "(status=pending/experimental)"
            )
        try:
            raw = self._get_json(
                f"{self.base_url}/auth",
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except Exception as exc:  # noqa: BLE001 — surface as transport error
            self._last_error = str(exc)
            raise BrokerTransportError(f"THS auth failed: {exc}") from exc
        self._authed = True
        return {"ok": True, "mode": "experimental", **(raw or {})}

    def place_orders(self, orders: list[dict[str, Any]], *, draft_id: str) -> dict[str, Any]:
        if not self._authed:
            raise BrokerTransportError("THS experimental transport not authenticated")
        if self._get_json is None:
            raise BrokerTransportError("experimental THS place_orders pending real wire-up")
        return self._get_json(
            f"{self.base_url}/orders",
            method="POST",
            json={"draftId": draft_id, "orders": orders, "account": self.account},
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def list_positions(self) -> list[dict[str, Any]]:
        if self._get_json is None:
            raise BrokerTransportError("experimental THS list_positions pending")
        raw = self._get_json(
            f"{self.base_url}/positions",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return list(raw.get("positions") or [])

    def list_orders(self) -> list[dict[str, Any]]:
        if self._get_json is None:
            raise BrokerTransportError("experimental THS list_orders pending")
        raw = self._get_json(
            f"{self.base_url}/orders",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return list(raw.get("orders") or [])

    def account(self) -> dict[str, Any]:
        if self._get_json is None:
            raise BrokerTransportError("experimental THS account pending")
        return self._get_json(
            f"{self.base_url}/account",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def poll_fills(self, *, since_execution_id: str | None = None) -> list[dict[str, Any]]:
        if self._get_json is None:
            raise BrokerTransportError("experimental THS poll_fills pending")
        raw = self._get_json(
            f"{self.base_url}/fills",
            params={"since": since_execution_id or ""},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return list(raw.get("fills") or [])


class ThsSimBroker:
    """External SIMULATE broker for Tonghuashun paper path (mock by default)."""

    name = "ths_sim"
    venue = "ths_sim"

    def __init__(
        self,
        transport: ThsTransport,
        *,
        ledger: PaperLedger | None = None,
        mode: str = "mock",
    ) -> None:
        self.transport = transport
        self.ledger = ledger or PaperLedger()
        self.mode = mode
        self._last_errors: list[str] = []
        self._fills: list[Fill] = []
        self._authed = False

    @classmethod
    def from_env(cls, **kwargs: Any) -> ThsSimBroker:
        mode = (os.environ.get("STOCK_PLATFORM_THS_MODE") or "mock").strip().lower()
        if mode not in {"mock", "experimental"}:
            raise BrokerConfigError(
                f"STOCK_PLATFORM_THS_MODE must be 'mock' or 'experimental', got {mode!r}"
            )
        if mode == "mock":
            fixture = kwargs.get("fixture_dir")
            transport: ThsTransport = MockThsTransport(
                fixture_dir=Path(fixture) if fixture else None
            )
        else:
            transport = ExperimentalThsHttpTransport(
                base_url=os.environ.get("STOCK_PLATFORM_THS_BASE_URL") or "",
                token=os.environ.get("STOCK_PLATFORM_THS_TOKEN") or "",
                account=os.environ.get("STOCK_PLATFORM_THS_ACCOUNT"),
                get_json=kwargs.get("get_json"),
            )
        ledger = kwargs.get("ledger")
        return cls(
            transport,
            ledger=ledger if isinstance(ledger, PaperLedger) else PaperLedger(),
            mode=mode,
        )

    def _ensure_auth(self) -> None:
        if self._authed:
            return
        try:
            self.transport.authenticate()
            self._authed = True
        except (BrokerConfigError, BrokerTransportError) as exc:
            self._last_errors.append(str(exc))
            raise

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
        # Reuse PaperLedger gates (timing / window / decision_only).
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
        draft["venue"] = self.venue
        draft["thsMode"] = self.mode
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
        try:
            draft = self.ledger.assert_executable(
                draft_id,
                profile=profile,
                now=now,
                max_draft_age_seconds=max_draft_age_seconds,
                market=market,
            )
        except (DraftBlocked, IdempotentReplay) as exc:
            if isinstance(exc, DraftBlocked):
                self._last_errors.append(str(exc))
            raise

        self._ensure_auth()
        try:
            placed = self.transport.place_orders(list(draft.get("orders") or []), draft_id=draft_id)
        except (BrokerConfigError, BrokerTransportError) as exc:
            self._last_errors.append(str(exc))
            raise

        paper_result = self.ledger.execute_draft(
            draft_id,
            profile=profile,
            now=now,
            max_draft_age_seconds=max_draft_age_seconds,
            market=market,
        )

        execution_id = str(placed.get("executionId") or paper_result["executionId"])
        accepted_at = str(paper_result.get("acceptedAt") or "")
        for i, raw in enumerate(placed.get("orders") or draft.get("orders") or []):
            intent = OrderIntent.from_dict(raw)
            px = float(raw.get("price") or 0.0)
            self._fills.append(
                Fill(
                    fill_id=str(raw.get("orderId") or f"{execution_id}:{i}"),
                    order_id=execution_id,
                    symbol=intent.symbol,
                    side=intent.side,
                    qty=intent.qty,
                    price=px,
                    filled_at=str(raw.get("filledAt") or accepted_at),
                    draft_id=draft_id,
                )
            )
        return {
            **paper_result,
            **placed,
            "executionId": execution_id,
            "draftId": draft_id,
            "broker": self.name,
            "venue": self.venue,
            "thsMode": self.mode,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }

    def status(self) -> dict[str, Any]:
        base = self.ledger.status()
        return {
            **base,
            "broker": self.name,
            "venue": self.venue,
            "thsMode": self.mode,
            "transportReady": self._authed,
            "httpStatus": "mock" if self.mode == "mock" else "experimental_pending",
            "lastErrors": list(self._last_errors),
            "banner": "SIMULATE · ths_sim · 非实盘 · 默认 mock",
        }

    def get_positions(self) -> list[Position]:
        self._ensure_auth()
        out: list[Position] = []
        for raw in self.transport.list_positions():
            out.append(
                Position(
                    symbol=str(raw["symbol"]),
                    qty=float(raw.get("qty") or 0),
                    avg_price=float(raw.get("avg_price") or raw.get("avgPrice") or 0),
                )
            )
        return out

    def get_orders(self) -> list[dict[str, Any]]:
        self._ensure_auth()
        return list(self.transport.list_orders())

    def get_account(self) -> AccountSnapshot:
        self._ensure_auth()
        raw = self.transport.account()
        return AccountSnapshot(
            cash=float(raw.get("cash") or 0),
            equity=float(raw.get("equity") or 0),
            currency=str(raw.get("currency") or "CNY"),
            account_id=str(raw.get("accountId") or "ths_sim"),
            environment="SIMULATE",
            live_trading_enabled=False,
            extras={"thsMode": self.mode},
        )

    def get_fills(self) -> list[Fill]:
        return list(self._fills)

    def poll_fills(self, *, since_execution_id: str | None = None) -> list[Fill]:
        self._ensure_auth()
        out: list[Fill] = []
        for raw in self.transport.poll_fills(since_execution_id=since_execution_id):
            out.append(
                Fill(
                    fill_id=str(raw.get("fillId") or uuid.uuid4()),
                    order_id=str(raw.get("orderId") or ""),
                    symbol=str(raw["symbol"]),
                    side=str(raw.get("side") or "buy"),
                    qty=float(raw.get("qty") or 0),
                    price=float(raw.get("price") or 0),
                    filled_at=str(raw.get("filledAt") or ""),
                    draft_id=raw.get("draftId"),
                )
            )
        return out
