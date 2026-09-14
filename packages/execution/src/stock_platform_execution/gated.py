"""Admission + timing gates for any BrokerPort (paper or ths_sim)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .admission import evaluate_admission
from .broker import BrokerPort
from .errors import DraftBlocked, ProfileBlocked
from .profile import validate_simulation_profile


def assert_sim_gates(
    *,
    data_ok: bool = True,
    hash_ok: bool = True,
    timing_ok: bool = True,
    idempotency_ok: bool = True,
    order_guards_ok: bool = True,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed SIMULATE admission; never enables live trading."""
    validate_simulation_profile(profile)
    admission = evaluate_admission(
        data_ok=data_ok,
        simulate_ok=True,
        live_off=True,
        hash_ok=hash_ok,
        timing_ok=timing_ok,
        idempotency_ok=idempotency_ok,
        order_guards_ok=order_guards_ok,
    )
    if not admission["passed"]:
        raise DraftBlocked(f"admission gates failed: {admission['criteria']}")
    return admission


class GatedBroker:
    """Wrap a BrokerPort; refuse build/execute when admission/profile gates fail."""

    def __init__(self, inner: BrokerPort, *, require_active_hash: bool = False) -> None:
        self.inner = inner
        self.require_active_hash = require_active_hash
        self._active_hash: str | None = None

    @property
    def name(self) -> str:
        return getattr(self.inner, "name", "gated")

    def set_active_hash(self, strategy_hash: str | None) -> None:
        self._active_hash = strategy_hash

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
        hash_ok = (not self.require_active_hash) or (
            bool(self._active_hash) and self._active_hash == strategy_hash
        )
        assert_sim_gates(hash_ok=hash_ok, profile=profile)
        return self.inner.build_draft(
            strategy_hash=strategy_hash,
            signal_trade_date=signal_trade_date,
            orders=orders,
            profile=profile,
            decision_only=decision_only,
            now=now,
            observed_raw_dates=observed_raw_dates,
            market=market,
        )

    def execute_draft(
        self,
        draft_id: str,
        *,
        profile: dict[str, Any] | None = None,
        now: datetime | None = None,
        max_draft_age_seconds: int = 600,
        market: str = "CN",
    ) -> dict[str, Any]:
        assert_sim_gates(profile=profile)
        return self.inner.execute_draft(
            draft_id,
            profile=profile,
            now=now,
            max_draft_age_seconds=max_draft_age_seconds,
            market=market,
        )

    def status(self) -> dict[str, Any]:
        snap = self.inner.status()
        try:
            admission = assert_sim_gates(
                hash_ok=(not self.require_active_hash) or bool(self._active_hash),
            )
        except (DraftBlocked, ProfileBlocked) as exc:
            admission = {"passed": False, "error": str(exc)}
        return {**snap, "admission": admission, "gated": True}

    def get_positions(self):  # type: ignore[no-untyped-def]
        return self.inner.get_positions()

    def get_orders(self):  # type: ignore[no-untyped-def]
        return self.inner.get_orders()

    def get_account(self):  # type: ignore[no-untyped-def]
        return self.inner.get_account()

    def get_fills(self):  # type: ignore[no-untyped-def]
        return self.inner.get_fills()
