"""Strategy content hash and draft → validated → active lifecycle."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import ActivationBlocked

HASH_SCHEMA = "stock-platform-strategy-v1"
STAGES = ("draft", "backtested", "validated", "active")
DEFAULT_SIMULATE_UNIVERSE = ["510300"]
AUTO_ACTIVATED_STATUS_ZH = "已自动激活默认纸面策略"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def strategy_hash(spec: dict[str, Any]) -> str:
    canonical = json.dumps(
        _normalize(spec),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_strategy_spec(
    *,
    universe: list[str],
    settings: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _normalize(
        {
            "hashSchema": HASH_SCHEMA,
            "universe": sorted(str(c) for c in universe),
            "settings": settings or {},
            "execution": {
                "allowedEnvironment": "SIMULATE",
                "liveTradingEnabled": False,
                **(execution or {}),
            },
        }
    )


class StrategyLifecycle:
    """In-memory draft/candidate/active registry (no broker)."""

    def __init__(self) -> None:
        self.draft: dict[str, Any] | None = None
        self.validated: dict[str, Any] | None = None
        self.active: dict[str, Any] | None = None

    def save_draft(self, spec: dict[str, Any]) -> dict[str, Any]:
        h = strategy_hash(spec)
        self.draft = {"stage": "draft", "strategyHash": h, "spec": spec, "validationFresh": False}
        return dict(self.draft)

    def mark_validated(self, expected_hash: str) -> dict[str, Any]:
        if not self.draft or self.draft["strategyHash"] != expected_hash:
            raise ActivationBlocked("draft hash mismatch; save draft before validate")
        self.validated = {
            "stage": "validated",
            "strategyHash": expected_hash,
            "validatedHash": expected_hash,
            "spec": self.draft["spec"],
        }
        self.draft["validationFresh"] = True
        return dict(self.validated)

    def activate(self, requested_hash: str, *, execution_safety_passed: bool) -> dict[str, Any]:
        if not execution_safety_passed:
            raise ActivationBlocked("executionSafety.passed is required to activate")
        if not self.validated or self.validated.get("validatedHash") != requested_hash:
            raise ActivationBlocked("validatedHash mismatch; explicit activate requires validated candidate")
        if self.draft and self.draft["strategyHash"] != requested_hash:
            # Editing a different draft must not change what activates.
            pass
        self.active = {
            "stage": "active",
            "strategyHash": requested_hash,
            "validatedHash": requested_hash,
            "spec": self.validated["spec"],
        }
        return dict(self.active)

    def ensure_default_simulate_active(
        self,
        *,
        universe: list[str] | None = None,
        execution_safety_passed: bool = True,
    ) -> dict[str, Any]:
        """Idempotent daily-path helper: create+activate a SIMULATE default if none active.

        Does not enable live trading. Callers must still enforce timing/admission gates
        on draft build / execute.
        """
        if self.active:
            return {
                "active": dict(self.active),
                "autoActivated": False,
                "statusMessage": None,
                "strategyHash": str(self.active["strategyHash"]),
            }
        if not execution_safety_passed:
            raise ActivationBlocked("executionSafety.passed is required to activate")
        codes = list(universe) if universe else list(DEFAULT_SIMULATE_UNIVERSE)
        spec = build_strategy_spec(universe=codes or list(DEFAULT_SIMULATE_UNIVERSE))
        saved = self.save_draft(spec)
        h = str(saved["strategyHash"])
        self.mark_validated(h)
        active = self.activate(h, execution_safety_passed=True)
        return {
            "active": dict(active),
            "autoActivated": True,
            "statusMessage": AUTO_ACTIVATED_STATUS_ZH,
            "strategyHash": h,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "draft": self.draft,
            "validated": self.validated,
            "active": self.active,
            "note": "saving a draft backup is not activation",
        }
