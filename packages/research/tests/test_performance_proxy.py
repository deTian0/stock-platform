"""performance_proxy：绩效代理台账（R4 / v4.7.1）。

锁定五件事：

1. **同形状转换** —— 回测成交 → 与真实台账逐字段同形状的决策行（``pending=False``）；
2. **口径刻死** —— 代理用扣费 ``net_ret``，真实是 T+N 固定持有，两侧**禁止混算**；
3. **分栏不合并** —— ``build_proxy_view`` 里不存在任何跨侧合计字段；
4. **复用单点** —— 两侧都走 ``performance.performance_summary``；
5. **CLI 接线** —— 长窗回测 → 代理台账 + 报告落盘（引擎被替身替换，零真实库）。

零网络、零真实行情库：fixture 全建在 ``tmp_path``。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from stock_platform_research import performance_proxy as pp
from stock_platform_research.performance import MIN_MEANINGFUL_SAMPLE, performance_summary
from stock_platform_research.performance_proxy import (
    PROXY_SOURCE,
    build_proxy_view,
    render_proxy_markdown,
    trades_to_decision_rows,
    write_proxy_ledger,
)

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _curve(n: int = 12) -> list[dict]:
    return [{"date": f"2026-01-{10 + i:02d}", "equity": 50000.0} for i in range(n)]


def _trade(code: str, entry_idx: int, held: int, gross: float, net: float) -> dict:
    return {
        "code": code,
        "asset_class": "stock",
        "entry_idx": entry_idx,
        "exit_idx": entry_idx + held,
        "held_days": held,
        "entry_price": 10.0,
        "exit_price": 11.0,
        "entry_value": 1000.0,
        "exit_value": 1100.0,
        "gross_ret": gross,
        "net_ret": net,
        "reason": "target",
        "exit_date": "2026-01-20",
    }


def _real_ledger(path: Path, n_settled: int, n_pending: int = 0) -> Path:
    lines: list[str] = []
    for i in range(n_settled):
        lines.append(
            f'{{"date": "2026-01-{10 + i:02d}", "symbol": "60000{i}", "rating": "Buy", '
            f'"raw": "+1.00%", "alpha": "+0.20%", "holding": "5d", "pending": false, "source": "brief"}}'
        )
    for i in range(n_pending):
        lines.append(
            f'{{"date": "2026-02-{10 + i:02d}", "symbol": "60010{i}", "rating": "Buy", '
            f'"raw": null, "alpha": null, "holding": "5d", "pending": true, "source": "brief"}}'
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. 同形状转换
# ---------------------------------------------------------------------------


def test_trades_to_decision_rows_shape() -> None:
    curve = _curve()
    rows = trades_to_decision_rows([_trade("600519", 2, 37, 4.0, 3.5)], equity_curve=curve)
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "600519"
    assert row["date"] == curve[2]["date"]  # 建仓日 = equity_curve[entry_idx].date
    assert row["rating"] == "Buy"
    assert row["raw"] == "+3.50%"  # net_ret（扣费）→ 百分号字符串
    assert row["alpha"] is None  # 代理侧无同窗基准超额，不编造
    assert row["holding"] == "37d"
    assert row["pending"] is False
    assert row["source"] == PROXY_SOURCE
    assert row["ledgerKind"] == "proxy"
    assert row["exitReason"] == "target"
    assert row["grossRetPct"] == 4.0


def test_trades_use_gross_when_asked() -> None:
    rows = trades_to_decision_rows(
        [_trade("000001", 0, 5, 4.0, 3.5)], equity_curve=_curve(), use_net=False
    )
    assert rows[0]["raw"] == "+4.00%"


def test_trades_bad_rows_are_dropped() -> None:
    rows = trades_to_decision_rows(
        [
            {"code": "", "net_ret": 1.0},  # 无 code
            {"code": "600519", "net_ret": None},  # 无收益
            _trade("000001", 0, 5, 4.0, 3.5),  # 正常
        ],
        equity_curve=_curve(),
    )
    assert [r["symbol"] for r in rows] == ["000001"]


def test_rows_feed_performance_summary() -> None:
    """代理行必须能被既有汇总算术直接吃下（同形状的硬证据）。"""
    trades = [_trade(f"60000{i}", i, 5, 3.0, 2.9) for i in range(MIN_MEANINGFUL_SAMPLE + 1)]
    rows = trades_to_decision_rows(trades, equity_curve=_curve(len(trades) + 1))
    stats = performance_summary(None, entries=rows)
    assert stats["settledCount"] == MIN_MEANINGFUL_SAMPLE + 1
    assert stats["pendingCount"] == 0
    assert stats["metrics"]["sample_note"] is None  # 已达门槛，无噪音提示
    assert stats["totalEntries"] == MIN_MEANINGFUL_SAMPLE + 1


def test_small_proxy_sample_flags_noise() -> None:
    rows = trades_to_decision_rows([_trade("600519", 0, 5, 1.0, 0.9)], equity_curve=_curve())
    stats = performance_summary(None, entries=rows)
    assert stats["metrics"]["sample_note"] is not None


# ---------------------------------------------------------------------------
# 2. 分栏不合并（禁止混算）——R4 的硬约束
# ---------------------------------------------------------------------------


def test_build_proxy_view_is_never_combinable(tmp_path: Path) -> None:
    real = _real_ledger(tmp_path / "real.jsonl", n_settled=2, n_pending=1)
    proxy_rows = trades_to_decision_rows(
        [_trade(f"60000{i}", i, 5, 3.0, 2.9) for i in range(3)],
        equity_curve=_curve(),
    )
    view = build_proxy_view(real_path=real, proxy_entries=proxy_rows)

    # 两侧分别汇总
    assert view["real"]["ledgerKind"] == "real"
    assert view["proxy"]["ledgerKind"] == "proxy"
    assert view["real"]["settledCount"] == 2
    assert view["proxy"]["settledCount"] == 3

    # 视图里**不存在**任何跨侧合计 / 合并字段
    for forbidden in ("total", "combined", "merged", "all", "sum", "settledCount"):
        assert forbidden not in view, f"top-level {forbidden!r} would be a mixed number"

    assert view["comparability"]["combinable"] is False
    assert "禁止混算" in view["comparability"]["reason"]
    assert view["comparability"]["singlePoint"] == "performance.performance_summary"


def test_build_proxy_view_sample_adequacy() -> None:
    view = build_proxy_view(
        real_entries=[{"date": "2026-01-10", "symbol": "600519", "rating": "Buy",
                       "raw": "+1.0%", "holding": "5d", "pending": False}],
        proxy_entries=trades_to_decision_rows(
            [_trade(f"60000{i}", i, 5, 3.0, 2.9) for i in range(MIN_MEANINGFUL_SAMPLE)],
            equity_curve=_curve(),
        ),
    )
    adeq = view["sampleAdequacy"]
    assert adeq["realSettled"] == 1
    assert adeq["proxySettled"] == MIN_MEANINGFUL_SAMPLE
    assert adeq["realAdequate"] is False
    assert adeq["proxyAdequate"] is True
    assert view["threshold"] == MIN_MEANINGFUL_SAMPLE


def test_build_proxy_view_missing_real_ledger_fails_closed(tmp_path: Path) -> None:
    view = build_proxy_view(
        real_path=tmp_path / "nope.jsonl",
        proxy_entries=trades_to_decision_rows([_trade("600519", 0, 5, 1.0, 0.9)], equity_curve=_curve()),
    )
    assert view["real"]["settledCount"] == 0
    assert view["real"]["totalEntries"] == 0
    assert view["proxy"]["settledCount"] == 1


def test_build_proxy_view_carries_provenance() -> None:
    view = build_proxy_view(
        real_path=None,
        proxy_entries=trades_to_decision_rows([_trade("600519", 0, 5, 1.0, 0.9)], equity_curve=_curve()),
        proxy_meta={"entrySource": "screener:lvrev", "start": "2025-01-01", "end": "2026-01-01"},
    )
    assert view["proxy"]["provenance"]["entrySource"] == "screener:lvrev"
    assert view["proxy"]["provenance"]["start"] == "2025-01-01"


# ---------------------------------------------------------------------------
# 3. 渲染
# ---------------------------------------------------------------------------


def test_render_markdown_has_sections_and_mixing_ban() -> None:
    view = build_proxy_view(
        real_entries=[{"date": "2026-01-10", "symbol": "600519", "rating": "Buy",
                       "raw": "+1.0%", "holding": "5d", "pending": False}],
        proxy_entries=trades_to_decision_rows(
            [_trade(f"60000{i}", i, 5, 3.0, 2.9) for i in range(3)], equity_curve=_curve()
        ),
    )
    md = render_proxy_markdown(view)
    for needle in (
        "# 绩效代理台账",
        "## 一、样本充分性",
        "## 二、真实台账",
        "## 三、代理台账",
        "## 四、口径差异（为何禁止混算）",
        "禁止混算",
    ):
        assert needle in md


def test_render_markdown_handles_empty_view() -> None:
    md = render_proxy_markdown({})
    assert isinstance(md, str)
    assert "# 绩效代理台账" in md


# ---------------------------------------------------------------------------
# 4. 台账 IO
# ---------------------------------------------------------------------------


def test_write_proxy_ledger_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "proxy.jsonl"
    rows = trades_to_decision_rows([_trade("600519", 0, 5, 1.0, 0.9)], equity_curve=_curve())
    write_proxy_ledger(path, rows)
    write_proxy_ledger(path, rows)  # 再写一遍
    assert len(pp.load_proxy_ledger(path)) == 1  # 覆盖，非追加


def test_load_proxy_ledger_missing_is_empty(tmp_path: Path) -> None:
    assert pp.load_proxy_ledger(tmp_path / "nope.jsonl") == []


# ---------------------------------------------------------------------------
# 5. 模块健康：零 providers 依赖（research 包硬约束）
# ---------------------------------------------------------------------------


def test_no_providers_dependency_at_module_level() -> None:
    src = Path(pp.__file__).read_text(encoding="utf-8")
    assert "stock_platform_providers" not in src


# ---------------------------------------------------------------------------
# 6. CLI
# ---------------------------------------------------------------------------


def test_cli_parser_accepts_years() -> None:
    from stock_platform_research.performance_proxy_cli import build_parser

    args = build_parser().parse_args(["--db", "x.db", "--years", "1"])
    assert args.years == 1
    assert args.universe == "stock"


def test_cli_resolve_window_defaults_to_years() -> None:
    from stock_platform_research.performance_proxy_cli import _resolve_window

    bars = pd.DataFrame({"date": ["2026-10-14"]})
    start, end = _resolve_window(bars, start=None, end=None, years=1)
    assert start == "2025-10-14"
    assert end is None  # 未显式给 end → 交回引擎（最后一日）


def test_cli_end_to_end_with_fake_engine(tmp_path: Path, monkeypatch) -> None:
    from stock_platform_research import performance_proxy_cli as cli

    db = tmp_path / "market.db"
    db.write_bytes(b"")  # is_file() 通过即可（引擎被替身替换）

    bars = pd.DataFrame(
        {"code": ["600519", "000001"], "date": ["2026-01-10", "2026-01-11"],
         "close": [10.0, 11.0], "pct_chg": [1.0, -1.0]}
    )
    monkeypatch.setattr(cli, "load_engine_bars", lambda *_a, **_k: bars)
    monkeypatch.setattr(cli, "filter_universe", lambda df, **_k: df)

    curve = _curve()
    trades = [_trade(f"60000{i}", i, 5, 3.0, 2.9) for i in range(MIN_MEANINGFUL_SAMPLE)]
    monkeypatch.setattr(
        cli,
        "run_portfolio_backtest",
        lambda *_a, **_k: {"ok": True, "reason": None, "trades": trades,
                           "equity_curve": curve, "metrics": {"n_trades": len(trades)}},
    )

    out_dir = tmp_path / "out"
    proxy_log = tmp_path / "proxy_ledger.jsonl"
    real_log = _real_ledger(tmp_path / "real.jsonl", n_settled=1)

    rc = cli.main([
        "--db", str(db),
        "--years", "1",
        "--real-log", str(real_log),
        "--proxy-log", str(proxy_log),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    assert (out_dir / "proxy_vs_real.json").is_file()
    assert (out_dir / "proxy_vs_real.md").is_file()
    assert proxy_log.is_file()
    assert len(pp.load_proxy_ledger(proxy_log)) == MIN_MEANINGFUL_SAMPLE


def test_cli_no_write_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    from stock_platform_research import performance_proxy_cli as cli

    db = tmp_path / "market.db"
    db.write_bytes(b"")
    bars = pd.DataFrame({"code": ["600519"], "date": ["2026-01-10"], "close": [10.0], "pct_chg": [1.0]})
    monkeypatch.setattr(cli, "load_engine_bars", lambda *_a, **_k: bars)
    monkeypatch.setattr(cli, "filter_universe", lambda df, **_k: df)
    monkeypatch.setattr(
        cli,
        "run_portfolio_backtest",
        lambda *_a, **_k: {"ok": True, "reason": None, "trades": [], "equity_curve": [], "metrics": {}},
    )
    out_dir = tmp_path / "out"
    rc = cli.main([
        "--db", str(db),
        "--no-write",
        "--proxy-log", str(tmp_path / "p.jsonl"),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    assert not out_dir.exists()
    assert not (tmp_path / "p.jsonl").exists()


def test_cli_missing_db_raises(tmp_path: Path) -> None:
    from stock_platform_research.performance_proxy_cli import main

    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "nope.db")])
