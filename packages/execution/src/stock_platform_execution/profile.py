"""Paper-only simulation profile gates."""

from __future__ import annotations

from typing import Any

from .errors import ProfileBlocked

ALLOWED_ENVIRONMENT = "SIMULATE"


def default_execution_profile() -> dict[str, Any]:
    return {
        "allowedEnvironment": ALLOWED_ENVIRONMENT,
        "liveTradingEnabled": False,
        "autoExecutePaperOrders": False,
        "tradeWindow": "09:35-10:00",
        "readyForPaperTrading": True,
        "status": "active_rehearsal",
    }


def validate_simulation_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Hard gates: SIMULATE only, live always off. Raises ProfileBlocked."""
    raw = profile or {}
    nested = raw.get("execution")
    if isinstance(nested, dict):
        execution = {**default_execution_profile(), **nested}
    else:
        execution = {**default_execution_profile(), **raw}

    env = execution.get("allowedEnvironment", ALLOWED_ENVIRONMENT)
    if env != ALLOWED_ENVIRONMENT:
        raise ProfileBlocked(f"allowedEnvironment must be {ALLOWED_ENVIRONMENT!r}, got {env!r}")
    if execution.get("liveTradingEnabled") is not False:
        raise ProfileBlocked("liveTradingEnabled must be False (paper-only)")
    if execution.get("readyForPaperTrading") is False:
        raise ProfileBlocked("readyForPaperTrading is False")
    status = execution.get("status", "active_rehearsal")
    if status not in {"active_rehearsal", "active", "validated"}:
        raise ProfileBlocked(f"unsupported profile status {status!r}")
    return execution
