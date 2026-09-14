"""In-memory paper draft ledger — SIMULATE only, idempotent accepts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from .errors import DraftBlocked, IdempotentReplay
from .profile import validate_simulation_profile
from .timing import (
    assert_signal_before_execution,
    china_now,
    execution_window_status,
    planned_execution_date,
    signal_bar_is_completed,
)


class PaperLedger:
    """Build / execute paper drafts without any broker SDK."""

    def __init__(self) -> None:
        self._accepted: dict[str, dict[str, Any]] = {}
        self._drafts: dict[str, dict[str, Any]] = {}

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
    ) -> dict[str, Any]:
        execution = validate_simulation_profile(profile)
        local = china_now(now)
        if not signal_bar_is_completed(signal_trade_date, local):
            raise DraftBlocked(f"signal bar for {signal_trade_date} is not completed")

        planned = planned_execution_date(signal_trade_date, observed_raw_dates)
        assert_signal_before_execution(signal_trade_date, planned)
        window = execution_window_status(planned, execution.get("tradeWindow"), local)

        blocked: list[str] = []
        eligible = window == "open" and not decision_only
        if decision_only:
            blocked.append("decision_only")
        if window in {"after_window", "stale"}:
            blocked.append(f"missed_window:{window}")
        if window in {"before_date", "before_window", "invalid"}:
            blocked.append(f"window:{window}")

        safe_orders = [] if (decision_only or not eligible) else list(orders)
        draft_id = str(uuid.uuid4())
        draft = {
            "draftId": draft_id,
            "strategyHash": strategy_hash,
            "signalTradeDate": signal_trade_date,
            "plannedExecutionDate": planned,
            "executionWindowStatus": window,
            "decisionOnly": decision_only,
            "executionEligible": eligible and not blocked,
            "orders": safe_orders,
            "blockedReasons": blocked,
            "generatedAt": local.isoformat(timespec="seconds"),
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
        }
        self._drafts[draft_id] = draft
        return dict(draft)

    def execute_draft(
        self,
        draft_id: str,
        *,
        profile: dict[str, Any] | None = None,
        now: datetime | None = None,
        max_draft_age_seconds: int = 600,
    ) -> dict[str, Any]:
        validate_simulation_profile(profile)
        if draft_id in self._accepted:
            prior = self._accepted[draft_id]
            raise IdempotentReplay(draft_id, str(prior["executionId"]))

        draft = self._drafts.get(draft_id)
        if not draft:
            raise DraftBlocked(f"unknown draftId {draft_id}")
        if draft.get("decisionOnly") or not draft.get("executionEligible"):
            raise DraftBlocked(
                f"draft not executable: decisionOnly={draft.get('decisionOnly')} "
                f"eligible={draft.get('executionEligible')} reasons={draft.get('blockedReasons')}"
            )
        if not draft.get("orders"):
            raise DraftBlocked("refusing to submit empty order list")

        local = china_now(now)
        generated = datetime.fromisoformat(str(draft["generatedAt"]))
        if generated.tzinfo is None:
            from .timing import CHINA_TZ

            generated = generated.replace(tzinfo=CHINA_TZ)
        age = (local - generated.astimezone(local.tzinfo)).total_seconds()
        if age > max_draft_age_seconds:
            raise DraftBlocked(f"draft older than {max_draft_age_seconds}s ({int(age)}s)")

        window = execution_window_status(
            str(draft["plannedExecutionDate"]),
            (profile or {}).get("tradeWindow") or "09:35-10:00",
            local,
        )
        if window != "open":
            raise DraftBlocked(f"execution window is {window}; late fill forbidden")

        execution_id = str(uuid.uuid4())
        result = {
            "executionId": execution_id,
            "draftId": draft_id,
            "accepted": True,
            "orders": list(draft["orders"]),
            "acceptedAt": local.isoformat(timespec="seconds"),
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "strategyHash": draft["strategyHash"],
        }
        self._accepted[draft_id] = result
        return dict(result)

    def status(self) -> dict[str, Any]:
        return {
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "draftCount": len(self._drafts),
            "acceptedCount": len(self._accepted),
            "banner": "SIMULATE · 实盘始终关闭",
        }
