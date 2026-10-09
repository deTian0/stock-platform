"""Tests for the ``B5`` online book review (``position_review.py``).

The point of this file is the **parity** with the backtest path: the online review
must be the same function on the same numbers, not a look-alike.
"""

from __future__ import annotations

import pytest

from stock_platform_research import backtest, rules
from stock_platform_research.position_review import format_review_markdown, review_positions
from stock_platform_research.rules import CooldownPolicy, DriftPolicy, ExitPolicy


def _holding(**kw):
    base = {
        "code": "600519.SH",
        "entry_price": 10.0,
        "price": 10.0,
        "peak": 10.0,
        "held_days": 50,
        "ma20": 3.0,
        "ma60": 2.0,
    }
    base.update(kw)
    return base


# ---------- parity with the backtest path ----------

def test_online_reason_equals_backtest_rule_reason_on_the_same_state():
    """Differential proof: same state ⇒ byte-identical reason from both paths."""
    state = dict(px=9.0, entry_price=10.0, target=10.5, peak=10.0, held_days=50)
    expected = rules.evaluate_exit(ma20=3.0, ma60=2.0, policy=ExitPolicy(), **state)
    assert expected is not None

    rev = review_positions([_holding(price=9.0)])
    assert rev["rows"][0]["action"] == "exit"
    assert rev["rows"][0]["reason"] == expected.reason
    assert rev["rows"][0]["ret_pct"] == pytest.approx(round(expected.ret_pct, 4))


def test_online_review_echoes_the_same_default_policy_the_backtest_uses():
    rev = review_positions([_holding()])
    assert rev["exitPolicy"] == {
        "stop_loss": 8.0,
        "take_profit": 0.0,
        "target_base": 5.0,
        "trail_stop_pct": 6.0,
        "trail_min_peak_ret": 2.0,
        "min_hold": 45,
        "max_hold_days": 60,
        "trail_min_held": 3,
    }
    assert rev["cooldownDays"] == 0
    assert rev["driftBand"] is None
    assert rev["environment"] == "SIMULATE"
    assert rev["liveTradingEnabled"] is False


def test_online_review_delegates_to_the_shared_functions():
    assert review_positions.__module__.startswith("stock_platform_research")
    # the rules objects the online path builds are the same classes the engine uses
    assert ExitPolicy is backtest.ExitPolicy
    assert CooldownPolicy is backtest.CooldownPolicy
    assert DriftPolicy is backtest.DriftPolicy


# ---------- actions ----------

def test_hold_when_nothing_fires():
    rev = review_positions([_holding(price=10.1)])
    row = rev["rows"][0]
    assert row["action"] == "hold"
    assert row["reason"] is None
    assert rev["counts"]["hold"] == 1
    assert rev["ok"] is True


def test_target_exit_through_the_shared_rule():
    rev = review_positions([_holding(price=10.6)])
    assert rev["rows"][0]["action"] == "exit"
    assert rev["rows"][0]["reason"] == "target(+6.0%)"


def test_drift_trim_and_add_need_a_policy_and_weights():
    off = review_positions([_holding(price=10.1, weight=0.5, target_weight=0.1)])
    assert off["rows"][0]["action"] == "hold"  # band disabled by default

    on = review_positions(
        [_holding(price=10.1, weight=0.5, target_weight=0.1)],
        drift_policy=DriftPolicy(band=0.30),
    )
    assert on["rows"][0]["action"] == "trim"
    assert on["rows"][0]["deviation"] == pytest.approx(4.0)

    light = review_positions(
        [_holding(price=10.1, weight=0.01, target_weight=0.1)],
        drift_policy=DriftPolicy(band=0.30),
    )
    assert light["rows"][0]["action"] == "add"


# ---------- guards ----------

def test_limit_down_defers_an_exit():
    rev = review_positions([_holding(price=9.0, pct_chg=-10.0)])
    row = rev["rows"][0]
    assert row["action"] == "exit"          # the rule still says exit …
    assert row["deferred"] is True          # … but today's sell cannot fill
    assert "跌停" in (row["note"] or "")


def test_no_limit_down_when_not_sealed():
    rev = review_positions([_holding(price=9.0, pct_chg=-3.0)])
    assert rev["rows"][0]["deferred"] is False


def test_pending_when_price_missing_never_guesses():
    rev = review_positions([_holding(price=None)])
    assert rev["rows"][0]["action"] == "pending"
    assert rev["rows"][0]["reason"] is None


def test_pending_when_entry_price_missing():
    rev = review_positions([{"code": "600519.SH", "price": 10.0}])
    assert rev["rows"][0]["action"] == "pending"


def test_empty_holdings_is_fail_closed():
    rev = review_positions([])
    assert rev["ok"] is False
    assert rev["failClosed"] is True
    assert rev["rows"] == []
    assert "空" in rev["reason"]


def test_cooldown_flag_is_reported():
    rev = review_positions(
        [_holding(price=10.1, last_exit_idx=10)],
        cooldown_policy=CooldownPolicy(cooldown_days=3),
        current_idx=11,
    )
    assert rev["rows"][0]["in_cooldown"] is True
    free = review_positions(
        [_holding(price=10.1, last_exit_idx=10)],
        cooldown_policy=CooldownPolicy(cooldown_days=3),
        current_idx=20,
    )
    assert free["rows"][0]["in_cooldown"] is False


def test_asset_class_is_reported_per_holding():
    rev = review_positions(
        [
            _holding(code="510300.SH", price=4.5, entry_price=4.0, held_days=5),
            _holding(code="600519.SH", price=10.1),
        ]
    )
    by_code = {r["code"]: r["asset_class"] for r in rev["rows"]}
    assert by_code == {"510300.SH": "etf", "600519.SH": "stock"}


def test_markdown_render_smoke():
    rev = review_positions([_holding(price=9.0), _holding(code="000001.SZ", price=10.1)])
    md = format_review_markdown(rev)
    assert "持仓复核" in md
    assert "600519.SH" in md
    assert "exit" in md


def test_held_days_unknown_is_flagged_never_silently_zero():
    rev = review_positions([{"code": "600519.SH", "entry_price": 10.0, "price": 10.1}])
    row = rev["rows"][0]
    assert row["held_days"] == 0
    assert row["held_days_unknown"] is True
    assert "持有天数未知" in (row["note"] or "")


# ---------- CLI plumbing (no DB) ----------

def test_load_holdings_accepts_bom_and_wrapped_shape(tmp_path):
    from stock_platform_research.position_review_cli import load_holdings

    p = tmp_path / "book.json"
    # Windows PowerShell writes a BOM with ``Set-Content -Encoding UTF8``
    p.write_bytes(b"\xef\xbb\xbf" + b'{"holdings":[{"code":"600519.SH","price":10}]}')
    assert load_holdings(p) == [{"code": "600519.SH", "price": 10}]


def test_cli_main_self_contained_returns_zero(tmp_path):
    import json as _json

    from stock_platform_research.position_review_cli import main

    p = tmp_path / "book.json"
    p.write_text(
        _json.dumps(
            [
                {
                    "code": "600519.SH",
                    "entry_price": 10.0,
                    "price": 10.1,
                    "held_days": 50,
                    "ma20": 3.0,
                    "ma60": 2.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    assert main(["--holdings", str(p), "--json"]) == 0


def test_cli_main_fail_closed_on_empty_book(tmp_path):
    from stock_platform_research.position_review_cli import main

    p = tmp_path / "book.json"
    p.write_text("[]", encoding="utf-8")
    assert main(["--holdings", str(p), "--json"]) == 2
