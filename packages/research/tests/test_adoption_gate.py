"""Unit tests for ``research.adoption_gate`` (milestone ``Y1``).

All fixtures are synthetic and deterministic — no network, no engine ``market.db``
(the one CLI end-to-end test builds its own tiny SQLite in ``tmp_path``).
"""

from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from stock_platform_research import adoption_gate as ag
from stock_platform_research import adoption_gate_cli as cli
from stock_platform_research.backtest import prepare_book_frame


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _bars(periods: int = 230, codes: int = 8, start: str = "2024-01-01") -> pd.DataFrame:
    """Deterministic bars: each code gets a different drift + amplitude (no RNG)."""
    days = pd.bdate_range(start, periods=periods)
    rows = []
    for i in range(codes):
        code = f"{600000 + i:06d}"
        drift = -0.0006 + 0.00035 * i
        price = 12.0 + i
        for j, d in enumerate(days):
            wave = 0.09 * ((j + 3 * i) % 21 - 10) / 10.0
            pct = drift + 0.012 * ((j + i) % 7 - 3) / 3.0
            price = max(1.0, price * (1.0 + pct) + wave * 0.05)
            rows.append(
                {
                    "code": code,
                    "date": d.date().isoformat(),
                    "close": round(price, 4),
                    "pct_chg": round(pct * 100.0, 4),
                }
            )
    return pd.DataFrame(rows)


def _feats(bars: pd.DataFrame | None = None) -> pd.DataFrame:
    return prepare_book_frame(bars if bars is not None else _bars(), universe="stock")


def _day_strings(feats: pd.DataFrame) -> list[str]:
    """``trade_date`` is ``datetime64`` here — normalise to ``YYYY-MM-DD`` labels."""
    return sorted(pd.to_datetime(feats["trade_date"]).dt.strftime("%Y-%m-%d").unique())


def _metrics(*, sharpe: float, mdd: float, win_rate: float, n_trades: int, total_return: float = 0.1):
    return {
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "win_rate": win_rate,
        "n_trades": n_trades,
        "total_return": total_return,
        "cagr": total_return,
        "final_equity": 50000.0 * (1.0 + total_return),
    }


def _pair(base_kw, cand_kw):
    return {"window": "w1", "baseline": _metrics(**base_kw), "candidate": _metrics(**cand_kw)}


GOOD_BASE = dict(sharpe=1.0, mdd=-0.15, win_rate=0.45, n_trades=20)
GOOD_CAND = dict(sharpe=1.30, mdd=-0.16, win_rate=0.47, n_trades=22)


# --------------------------------------------------------------------------- #
# windows
# --------------------------------------------------------------------------- #
def test_build_windows_is_disjoint_and_ascending():
    wins = ag.build_windows("2026-09-30", years=1, count=3)
    assert [w["label"] for w in wins] == ["w1", "w2", "w3"]
    assert wins[0]["end"] < wins[1]["start"]  # strictly disjoint
    assert wins[2]["end"] == "2026-09-30"
    # each window is ~365 days
    for w in wins:
        span = (pd.Timestamp(w["end"]) - pd.Timestamp(w["start"])).days
        assert span == 365


def test_build_windows_clamps_bad_counts():
    assert len(ag.build_windows("2026-01-01", years=0, count=0)) == 1


def test_slice_window_filters_inclusive():
    feats = _feats()
    days = _day_strings(feats)
    lo, hi = days[70], days[100]
    cut = ag.slice_window(feats, lo, hi)
    assert not cut.empty
    assert _day_strings(cut)[0] == lo
    assert _day_strings(cut)[-1] == hi
    assert len(cut) < len(feats)


def test_slice_window_empty_frame_passthrough():
    empty = pd.DataFrame(columns=["code", "trade_date", "close"])
    assert ag.slice_window(empty, "2025-01-01", "2025-12-31").empty


# --------------------------------------------------------------------------- #
# decide_adoption (pure)
# --------------------------------------------------------------------------- #
def test_decide_adoption_all_windows_pass():
    out = ag.decide_adoption([_pair(GOOD_BASE, GOOD_CAND), _pair(GOOD_BASE, GOOD_CAND)])
    assert out["verdict"] == ag.VERDICT_ADOPT
    assert out["counts"]["pass"] == 2 and out["counts"]["fail"] == 0
    assert out["reasons"] == []
    assert out["meanDelta"]["sharpe"] == pytest.approx(0.30)


def test_decide_adoption_single_failing_window_rejects():
    out = ag.decide_adoption(
        [_pair(GOOD_BASE, GOOD_CAND), _pair(GOOD_BASE, dict(GOOD_CAND, sharpe=0.90))]
    )
    assert out["verdict"] == ag.VERDICT_REJECT
    assert out["counts"]["fail"] == 1
    assert out["failingWindows"] == ["w1"]
    assert any("夏普" in r for r in out["reasons"])


def test_decide_adoption_any_window_relaxes_to_majority():
    pairs = [
        _pair(GOOD_BASE, GOOD_CAND),
        _pair(GOOD_BASE, dict(GOOD_CAND, sharpe=0.90)),
        _pair(GOOD_BASE, GOOD_CAND),
    ]
    strict = ag.decide_adoption(pairs)
    relaxed = ag.decide_adoption(pairs, ag.AdoptionRule(require_all_windows=False))
    assert strict["verdict"] == ag.VERDICT_REJECT
    assert relaxed["verdict"] == ag.VERDICT_ADOPT


def test_decide_adoption_insufficient_when_too_few_trades():
    out = ag.decide_adoption([_pair(dict(GOOD_BASE, n_trades=3), dict(GOOD_CAND, n_trades=4))])
    assert out["verdict"] == ag.VERDICT_INSUFFICIENT
    assert out["windows"][0]["verdict"] == ag.WINDOW_INSUFFICIENT
    assert out["counts"]["insufficient"] == 1


def test_decide_adoption_blocks_on_drawdown_deterioration():
    out = ag.decide_adoption([_pair(GOOD_BASE, dict(GOOD_CAND, mdd=-0.40))])
    assert out["verdict"] == ag.VERDICT_REJECT
    assert "drawdown" in out["windows"][0]["blockingChecks"]


def test_decide_adoption_blocks_on_winrate_drop():
    out = ag.decide_adoption([_pair(GOOD_BASE, dict(GOOD_CAND, win_rate=0.10))])
    assert out["verdict"] == ag.VERDICT_REJECT
    assert "winrate" in out["windows"][0]["blockingChecks"]


def test_decide_adoption_missing_metrics_is_not_a_pass():
    out = ag.decide_adoption([_pair(GOOD_BASE, dict(GOOD_CAND, sharpe=None))])
    assert out["verdict"] == ag.VERDICT_REJECT
    assert out["windows"][0]["blockingChecks"] == ["sharpe"]


def test_decide_adoption_rule_is_echoed():
    rule = ag.AdoptionRule(min_sharpe_margin=0.2, min_trades=5)
    out = ag.decide_adoption([_pair(GOOD_BASE, GOOD_CAND)], rule)
    assert out["rule"]["min_sharpe_margin"] == 0.2
    assert out["rule"]["min_trades"] == 5


# --------------------------------------------------------------------------- #
# candidate specs
# --------------------------------------------------------------------------- #
def test_baseline_spec_is_not_a_candidate():
    assert ag.BASELINE_SPEC.name not in ag.CANDIDATE_REGISTRY
    assert ag.BASELINE_SPEC.neutralize is False


def test_registry_matches_default_candidates():
    assert set(ag.CANDIDATE_REGISTRY) == {s.name for s in ag.DEFAULT_CANDIDATES}


def test_candidate_summary_expands_neutralize_params():
    off = ag.CANDIDATE_REGISTRY["gate_070"].to_summary()
    on = ag.CANDIDATE_REGISTRY["neutralized"].to_summary()
    assert off["neutralize"] is False and off["neutralizeParams"] is None
    assert on["neutralize"] is True and on["neutralizeParams"]["mode"] == "demean"
    assert off["minPickScore"] == 0.70


# --------------------------------------------------------------------------- #
# engine runs
# --------------------------------------------------------------------------- #
def test_run_candidate_baseline_returns_metric_keys():
    out = ag.run_candidate(_feats(), ag.BASELINE_SPEC)
    assert set(ag.AB_METRIC_KEYS) <= set(out["metrics"])
    assert out["nDays"] > 0


def test_run_candidate_neutralized_runs_without_industry_column():
    spec = ag.CANDIDATE_REGISTRY["neutralized"]
    out = ag.run_candidate(_feats(), spec)
    assert out["metrics"] is not None
    assert "sharpe" in out["metrics"]


# --------------------------------------------------------------------------- #
# evaluate_adoption end-to-end (synthetic)
# --------------------------------------------------------------------------- #
def test_evaluate_adoption_full_report():
    feats = _feats()
    days = _day_strings(feats)
    wins = [
        {"label": "w1", "start": days[65], "end": days[140]},
        {"label": "w2", "start": days[141], "end": days[-1]},
    ]
    payload = ag.evaluate_adoption(feats, windows=wins, generated_at="2026-10-14")
    assert payload["ok"] is True
    assert payload["generatedAt"] == "2026-10-14"
    assert len(payload["windows"]) == 2
    assert len(payload["candidates"]) == len(ag.DEFAULT_CANDIDATES)
    verdicts = {b["decision"]["verdict"] for b in payload["candidates"]}
    assert verdicts <= {ag.VERDICT_ADOPT, ag.VERDICT_REJECT, ag.VERDICT_INSUFFICIENT}
    assert set(payload["verdictCounts"]) == {
        ag.VERDICT_ADOPT,
        ag.VERDICT_REJECT,
        ag.VERDICT_INSUFFICIENT,
    }
    assert payload["liveTradingEnabled"] is False
    assert payload["environment"] == "SIMULATE"


def test_evaluate_adoption_subset_of_candidates():
    feats = _feats()
    days = _day_strings(feats)
    wins = [{"label": "w1", "start": days[65], "end": days[-1]}]
    only = [ag.CANDIDATE_REGISTRY["gate_070"]]
    payload = ag.evaluate_adoption(feats, candidates=only, windows=wins)
    assert [b["name"] for b in payload["candidates"]] == ["gate_070"]


def test_evaluate_adoption_no_candidates_is_still_ok():
    feats = _feats()
    days = _day_strings(feats)
    wins = [{"label": "w1", "start": days[65], "end": days[-1]}]
    payload = ag.evaluate_adoption(feats, candidates=[], windows=wins)
    assert payload["ok"] is True
    assert payload["candidates"] == [] and payload["recommended"] == []


def test_evaluate_adoption_empty_inputs_fail_closed():
    assert ag.evaluate_adoption(pd.DataFrame(), windows=[{"label": "w1", "start": "a", "end": "b"}])["ok"] is False
    assert ag.evaluate_adoption(_feats(), windows=[])["ok"] is False


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def test_render_markdown_has_needles():
    feats = _feats()
    days = _day_strings(feats)
    wins = [{"label": "w1", "start": days[65], "end": days[-1]}]
    md = ag.render_adoption_markdown(ag.evaluate_adoption(feats, windows=wins))
    for needle in ("# 策略采纳闸门报告", "## 采纳规则（事前登记）", "## 裁决总表", "## 逐窗明细", "## 建议"):
        assert needle in md


def test_render_markdown_fail_closed():
    md = ag.render_adoption_markdown({"ok": False, "reason": "no bars in range"})
    assert "no bars in range" in md


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _make_db(path, *, with_industry: bool = True) -> None:
    bars = _bars()
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE daily_price (code TEXT, date TEXT, close REAL, pct_chg REAL)")
    con.executemany(
        "INSERT INTO daily_price VALUES (?,?,?,?)",
        list(bars[["code", "date", "close", "pct_chg"]].itertuples(index=False, name=None)),
    )
    con.execute("CREATE TABLE fundamentals (code TEXT, industry TEXT, name TEXT)")
    if with_industry:
        industries = ["银行", "白酒", "医药", "电子"]
        con.executemany(
            "INSERT INTO fundamentals VALUES (?,?,?)",
            [
                (f"{600000 + i:06d}", industries[i % len(industries)], f"票{i}")
                for i in range(8)
            ],
        )
    con.commit()
    con.close()


def test_cli_resolve_candidates():
    assert len(cli._resolve_candidates("")) == len(ag.DEFAULT_CANDIDATES)
    assert cli._resolve_candidates("none") == []
    assert [s.name for s in cli._resolve_candidates("gate_070")] == ["gate_070"]
    with pytest.raises(SystemExit):
        cli._resolve_candidates("does-not-exist")


def test_cli_last_bar_date(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db)
    assert cli._last_bar_date(str(db)) == _bars()["date"].max()


def test_cli_end_to_end_writes_report(tmp_path):
    db = tmp_path / "market.db"
    _make_db(db)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        [
            "--db", str(db),
            "--start", days[65],
            "--end", days[-1],
            "--candidates", "neutralized,gate_070",
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 0
    out = tmp_path / "out"
    payload = json.loads((out / "adoption_gate.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["universe"] == "stock"
    assert len(payload["candidates"]) == 2
    assert (out / "adoption_gate.md").is_file()


def test_cli_no_write_and_json_flag(tmp_path, capsys):
    db = tmp_path / "market.db"
    _make_db(db, with_industry=False)
    days = sorted(_bars()["date"].unique())
    code = cli.main(
        [
            "--db", str(db),
            "--start", days[65],
            "--end", days[-1],
            "--candidates", "none",
            "--no-write",
            "--json",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "策略采纳闸门报告" in printed
    assert '"ok": true' in printed.replace('"ok":true', '"ok": true')
    assert not (tmp_path / "data").exists()


def test_cli_missing_db_exits(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--db", str(tmp_path / "nope.db")])
