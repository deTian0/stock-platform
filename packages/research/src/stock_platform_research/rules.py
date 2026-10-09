"""Trading-rule **single source of truth**: exit / cooldown / position drift (``B5``).

Why this module exists
----------------------
``V2-code-review-20260905`` §「检查重点」item 5: *「回测与在线规则是否一致；冷静期、
退出条件和持仓偏差是否存在逻辑盲区。」* Until ``B5`` the whole exit decision
(stop-loss / take-profit / target / trend-break / trailing / max-hold) lived
**inline inside** :func:`backtest.run_portfolio_backtest` — the *backtest* path
only. Any online / daily book review would have had to re-implement it, and the
two copies would silently drift apart. That is exactly the "duplicate
implementation" risk the ``C`` domain warns about, and the fifth item on the
``L`` domain's carry-over list.

This module is the **single definition**. Two call paths consume it:

* **backtest** → :func:`backtest.run_portfolio_backtest` (history replay)
* **online**   → :func:`position_review.review_positions` (live book review)

The single-definition contract is asserted in ``tests/test_rules.py``::

    backtest.evaluate_exit is rules.evaluate_exit   →  True
    backtest.ExitPolicy    is rules.ExitPolicy      →  True

Everything here is a **pure function** or a frozen dataclass — no pandas, no
I/O — so both callers may pass plain scalars and stay trivially comparable.
``liveTradingEnabled`` stays ``False``: this module decides *what the rules say*,
never sends an order.

Conventions (frozen in ``docs/contracts/trading-rules.md``)
----------------------------------------------------------
- ``ret_pct`` / ``peak_ret`` are **percent points** (``-8.0`` = −8 %), not fractions.
- ``held_days`` is **sessions since entry** (entry session = 0).
- the running ``peak`` is expected to **already include today's close** — callers
  advance it with :func:`advance_peak` *before* :func:`evaluate_exit`.
- ``min_hold`` gates the *discretionary* exits (target / trend-break / trailing /
  max-hold) but **never** the protective ones (stop-loss / take-profit).
- defaults reproduce the ``B1``–``B4`` baseline decision-for-decision; the new
  policies (``cooldown_days = 0``, ``band = None``) are **off by default**.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .portfolio import norm_code  # reused, never re-defined (no import cycle)

# --- daily price limits -----------------------------------------------------
# Main board ±10 %; STAR (688) / ChiNext (300|301) ±20 %; ST ±5 %.
_MAIN_LIMIT = 0.10
_STAR_CHINEXT_LIMIT = 0.20
_ST_LIMIT = 0.05
# Percentage-point tolerance used by the B1 backtest when comparing ``pct_chg``.
LIMIT_EPS = 0.01


def limit_pct(code: Any, *, is_st: bool = False) -> float:
    """Daily price limit as a fraction: ST ±5 % / STAR+ChiNext (30/68) ±20 % / main ±10 %."""
    c = norm_code(code)
    if is_st:
        return _ST_LIMIT
    return _STAR_CHINEXT_LIMIT if c.startswith(("30", "68")) else _MAIN_LIMIT


def is_limit_up(code: Any, pct_chg: Any, *, is_st: bool = False, eps: float = LIMIT_EPS) -> bool:
    """Sealed **limit-up** ⇒ a *buy* cannot fill at the reference close.

    ``pct_chg`` is compared verbatim against ``±limit × 100`` (percent points),
    exactly as the ``B1`` engine does. The engine dump ships ``pct_chg`` on a
    *mixed* scale (fractions for most rows, percent points for some) — see the
    known-limitations note in the contract; ``B5`` deliberately does **not** change
    that comparison, because doing so would move the baseline.
    """
    if pct_chg is None:
        return False
    try:
        v = float(pct_chg)
    except (TypeError, ValueError):
        return False
    if math.isnan(v):
        return False
    return v >= limit_pct(code, is_st=is_st) * 100.0 - eps


def is_limit_down(code: Any, pct_chg: Any, *, is_st: bool = False, eps: float = LIMIT_EPS) -> bool:
    """Sealed **limit-down** ⇒ a *sell* cannot fill; the exit rolls to next session."""
    if pct_chg is None:
        return False
    try:
        v = float(pct_chg)
    except (TypeError, ValueError):
        return False
    if math.isnan(v):
        return False
    return v <= -limit_pct(code, is_st=is_st) * 100.0 + eps


def _num(x: Any) -> float | None:
    """``None`` for missing / NaN / non-numeric — never fabricated to ``0``."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


# --- policies ---------------------------------------------------------------


@dataclass(frozen=True)
class ExitPolicy:
    """Exit knobs. Defaults are the ``B1``–``B4`` baseline values, unchanged."""

    stop_loss: float = 8.0            # hard stop: ret_pct ≤ −8 %
    take_profit: float = 0.0          # 0 = disabled (baseline had it off)
    target_base: float = 5.0          # target = entry × (1 + 5 %)
    trail_stop_pct: float = 6.0       # give back ≥6 % from the peak
    trail_min_peak_ret: float = 2.0   # …only once the peak was ≥+2 %
    min_hold: int = 45                # discretionary exits need ≥45 sessions
    max_hold_days: int = 60           # safety valve
    trail_min_held: int = 3           # trailing needs held_days > 3

    def target_price(self, entry_price: float) -> float:
        """Take-profit target for an entry fill — the *only* place this is defined."""
        return float(entry_price) * (1.0 + self.target_base / 100.0)


@dataclass(frozen=True)
class CooldownPolicy:
    """冷静期: after an exit, block re-entry into the same code for N sessions.

    ``cooldown_days = 0`` (default) disables it ⇒ the backtest is bit-for-bit the
    ``B1``–``B4`` baseline. The exit is booked at index ``E``; entries are blocked
    while ``current_idx − E < cooldown_days``, so ``cooldown_days = 1`` already
    blocks **same-session** re-entry (exit and entry both price at the close).
    """

    cooldown_days: int = 0

    @property
    def active(self) -> bool:
        return self.cooldown_days > 0

    def blocks(self, *, last_exit_idx: int | None, current_idx: int) -> bool:
        if self.cooldown_days <= 0 or last_exit_idx is None:
            return False
        return (current_idx - last_exit_idx) < self.cooldown_days

    def remaining(self, *, last_exit_idx: int | None, current_idx: int) -> int:
        """Sessions still blocked (0 when free) — for reporting only."""
        if not self.blocks(last_exit_idx=last_exit_idx, current_idx=current_idx):
            return 0
        assert last_exit_idx is not None
        return int(self.cooldown_days - (current_idx - last_exit_idx))


@dataclass(frozen=True)
class DriftPolicy:
    """持仓偏差: act when a position weight deviates from its target by ``band``.

    ``band`` is a **relative** deviation (``0.30`` = ±30 % of the target weight).
    ``band = None`` (default) disables the rule ⇒ no rebalancing signal and the
    backtest is unchanged.
    """

    band: float | None = None

    @property
    def active(self) -> bool:
        return self.band is not None and self.band > 0


# --- decisions --------------------------------------------------------------


@dataclass
class PositionState:
    """A single long position. Mutable: the caller advances ``peak`` in place."""

    code: str
    entry_price: float
    shares: float
    entry_idx: int
    target: float
    peak: float


@dataclass(frozen=True)
class ExitDecision:
    """Why (and how far) a position should be closed on this session."""

    reason: str
    ret_pct: float
    held_days: int


@dataclass(frozen=True)
class DriftDecision:
    """What the position-drift rule says: ``hold`` / ``trim`` / ``add``."""

    action: str
    deviation: float | None


def advance_peak(peak: float, px: float) -> float:
    """Running peak for the trailing stop — shared by both call paths."""
    return float(px) if float(px) > float(peak) else float(peak)


def evaluate_exit(
    *,
    px: float,
    entry_price: float,
    target: float,
    peak: float,
    held_days: int,
    ma20: Any = None,
    ma60: Any = None,
    policy: ExitPolicy | None = None,
) -> ExitDecision | None:
    """The **one** exit decision used by backtest *and* online review.

    Order and reason strings are frozen (``docs/contracts/trading-rules.md``);
    ``tests/test_rules.py`` pins each branch. Returns ``None`` ⇒ keep holding.

    ``peak`` must already include today's close (see :func:`advance_peak`).
    ``ma20`` / ``ma60`` accept ``None`` (or NaN) for "not available".
    """
    p = policy or ExitPolicy()
    ret_pct = (float(px) / float(entry_price) - 1.0) * 100.0
    peak_ret = (float(peak) / float(entry_price) - 1.0) * 100.0

    reason: str | None = None
    if ret_pct <= -p.stop_loss:
        reason = f"stop_loss({ret_pct:+.1f}%)"
    elif p.take_profit > 0 and ret_pct >= p.take_profit:
        reason = f"take_profit({ret_pct:+.1f}%)"
    elif int(held_days) >= p.min_hold:
        m20 = _num(ma20)
        m60 = _num(ma60)
        if float(px) >= float(target):
            reason = f"target({ret_pct:+.1f}%)"
        elif m20 is not None and m60 is not None and m20 <= m60:
            reason = f"trend_break({ret_pct:+.1f}%)"
        elif (
            int(held_days) > p.trail_min_held
            and peak_ret >= p.trail_min_peak_ret
            and float(peak) > 0
            and (float(peak) - float(px)) / float(peak) >= p.trail_stop_pct / 100.0
        ):
            reason = f"trail_stop({ret_pct:+.1f}%)"
        elif int(held_days) >= p.max_hold_days:
            reason = f"max_hold({int(held_days)}d)"

    if reason is None:
        return None
    return ExitDecision(reason=reason, ret_pct=ret_pct, held_days=int(held_days))


def evaluate_drift(
    *,
    weight: Any,
    target_weight: Any,
    policy: DriftPolicy | None = None,
) -> DriftDecision:
    """Weight-drift rule: ``hold`` / ``trim`` (too heavy) / ``add`` (too light).

    Missing inputs or a disabled policy ⇒ ``hold`` with ``deviation = None`` —
    never a fabricated instruction.
    """
    p = policy or DriftPolicy()
    w = _num(weight)
    tw = _num(target_weight)
    if not p.active or w is None or tw is None or tw <= 0:
        return DriftDecision(action="hold", deviation=None)
    dev = (w - tw) / tw
    assert p.band is not None
    if dev > p.band:
        return DriftDecision(action="trim", deviation=dev)
    if dev < -p.band:
        return DriftDecision(action="add", deviation=dev)
    return DriftDecision(action="hold", deviation=dev)


def in_cooldown(
    code: Any,
    *,
    last_exit_idx: int | None,
    current_idx: int,
    policy: CooldownPolicy | None = None,
) -> bool:
    """Convenience wrapper: is ``code`` blocked from (re-)entry right now?"""
    return (policy or CooldownPolicy()).blocks(
        last_exit_idx=last_exit_idx, current_idx=current_idx
    )


def portfolio_weights(values: Iterable[float]) -> list[float]:
    """Normalise holding market values to weights (empty ⇒ ``[]``)."""
    vals = [max(float(v), 0.0) for v in values]
    total = sum(vals)
    if total <= 0:
        return []
    return [v / total for v in vals]


__all__ = [
    "LIMIT_EPS",
    "CooldownPolicy",
    "DriftDecision",
    "DriftPolicy",
    "ExitDecision",
    "ExitPolicy",
    "PositionState",
    "advance_peak",
    "evaluate_drift",
    "evaluate_exit",
    "in_cooldown",
    "is_limit_down",
    "is_limit_up",
    "limit_pct",
    "portfolio_weights",
]
