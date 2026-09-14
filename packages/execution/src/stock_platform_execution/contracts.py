"""Broker-facing order / fill / position / account contracts (SIMULATE only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    qty: float
    order_type: str = "market"
    limit_price: float | None = None
    client_order_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> OrderIntent:
        return cls(
            symbol=str(raw["symbol"]),
            side=str(raw.get("side") or "buy").lower(),
            qty=float(raw.get("qty") or raw.get("quantity") or 0),
            order_type=str(raw.get("order_type") or raw.get("orderType") or "market"),
            limit_price=(
                float(raw["limit_price"])
                if raw.get("limit_price") is not None
                else (float(raw["limitPrice"]) if raw.get("limitPrice") is not None else None)
            ),
            client_order_id=(
                str(raw["client_order_id"])
                if raw.get("client_order_id") is not None
                else (str(raw["clientOrderId"]) if raw.get("clientOrderId") is not None else None)
            ),
        )


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    filled_at: str
    draft_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    avg_price: float = 0.0
    market_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    equity: float
    currency: str = "CNY"
    account_id: str = "paper"
    environment: str = "SIMULATE"
    live_trading_enabled: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["liveTradingEnabled"] = d.pop("live_trading_enabled")
        d["accountId"] = d.pop("account_id")
        return d
