"""Admission checklist — pass means controlled paper access, not proven alpha."""

from __future__ import annotations

from typing import Any


def evaluate_admission(
    *,
    data_ok: bool,
    simulate_ok: bool,
    live_off: bool,
    hash_ok: bool,
    timing_ok: bool,
    idempotency_ok: bool,
    order_guards_ok: bool,
) -> dict[str, Any]:
    criteria = {
        "data": data_ok,
        "simulate": simulate_ok,
        "live_off": live_off,
        "hash": hash_ok,
        "timing": timing_ok,
        "idempotency": idempotency_ok,
        "order_guards": order_guards_ok,
    }
    passed = all(criteria.values())
    return {
        "passed": passed,
        "criteria": criteria,
        "disclaimer": "Admission pass means controlled SIMULATE access only — not proven performance.",
    }
