"""Strategy A/B — a default-off sidecar on the daily path **and** the S1 full A/B.

Two surfaces share this module:

* **M-R5 sidecar** (``run_strategy_ab_sidecar`` / ``attach_strategy_ab``): a
  light **PIT-panel** compare of two packaged configs, attached to the brief only
  when opted in (``STOCK_PLATFORM_STRATEGY_AB=1`` or ``strategyAb=true``). Default
  **off**; never replaces primary lvrev picks.
* **S1 full A/B** (``compare_strategy_ab_engine`` / ``compare_strategy_ab_from_bars``):
  run **two strategy configs through the same portfolio engine**. ``S1`` closes the
  ``U7 完整版`` gap — a factor / gate change now carries a *复盘对比* (review +
  full portfolio metrics) and both arms are provably judged by one loop
  (:func:`book_replay.replay_book`, the ``X4`` single definition), so the two
  columns of an A/B are comparable without re-normalisation.

The PIT sidecar is *light* and path-agnostic; the S1 side is the same engine the
backtest and the logged-picks replay use. Both default to **not** touching the
daily recommend path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .backtest import prepare_book_frame
from .book_replay import (
    EntryProvider,
    ReplayParams,
    replay_book,
    screener_entry_provider,
)
from .portfolio import compute_metrics
from .strategy_config import (
    StrategyConfig,
    compare_strategy_configs,
    default_strategy_config_dir,
    load_strategy_config,
)

ENV_STRATEGY_AB = "STOCK_PLATFORM_STRATEGY_AB"
ENV_STRATEGY_AB_A = "STOCK_PLATFORM_STRATEGY_AB_A"
ENV_STRATEGY_AB_B = "STOCK_PLATFORM_STRATEGY_AB_B"
DEFAULT_CONFIG_A = "lvrev-default-v1"
DEFAULT_CONFIG_B = "lvrev-rev-heavy-v1"


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def strategy_ab_enabled(*, env: Mapping[str, str] | None = None, request_flag: bool = False) -> bool:
    """True when env opt-in or explicit per-request flag is set."""
    if request_flag:
        return True
    source = env if env is not None else os.environ
    return _truthy(source.get(ENV_STRATEGY_AB))


def strategy_ab_status(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    enabled = strategy_ab_enabled(env=source)
    return {
        "enabled": enabled,
        "defaultOnDailyPath": False,
        "envVar": ENV_STRATEGY_AB,
        "configA": (source.get(ENV_STRATEGY_AB_A) or DEFAULT_CONFIG_A).strip()
        or DEFAULT_CONFIG_A,
        "configB": (source.get(ENV_STRATEGY_AB_B) or DEFAULT_CONFIG_B).strip()
        or DEFAULT_CONFIG_B,
        "note": (
            "默认关闭；设 STOCK_PLATFORM_STRATEGY_AB=1 或请求 strategyAb=true 后，"
            "推荐响应附带 strategyAb 对比摘要，不替换主路径 picks。"
        ),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


def _resolve_config_ref(ref: str) -> Path | Mapping[str, Any]:
    raw = (ref or "").strip()
    root = default_strategy_config_dir()
    candidate = root / f"{raw}.json" if not raw.endswith(".json") else root / Path(raw).name
    if candidate.is_file():
        return candidate
    path = Path(raw)
    if path.is_file():
        return path
    # Allow packaged id without suffix.
    packaged = root / f"{raw}.json"
    if packaged.is_file():
        return packaged
    raise FileNotFoundError(f"strategy config not found: {ref}")


def run_strategy_ab_sidecar(
    panel: pd.DataFrame,
    *,
    config_a: str | None = None,
    config_b: str | None = None,
    panel_source: str = "caller",
    panel_note: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compare two packaged configs on an injected panel (research sidecar)."""
    source = env if env is not None else os.environ
    a_ref = (config_a or source.get(ENV_STRATEGY_AB_A) or DEFAULT_CONFIG_A).strip()
    b_ref = (config_b or source.get(ENV_STRATEGY_AB_B) or DEFAULT_CONFIG_B).strip()
    a_path = _resolve_config_ref(a_ref)
    b_path = _resolve_config_ref(b_ref)
    # Validate load early for clearer errors.
    load_strategy_config(a_path)
    load_strategy_config(b_path)
    cmp = compare_strategy_configs(panel, a_path, b_path)
    return {
        "ok": True,
        "enabled": True,
        "onDailyPath": True,
        "replacesPicks": False,
        "configA": a_ref,
        "configB": b_ref,
        "winner": cmp.get("winner"),
        "deltaFinalEquity": cmp.get("deltaFinalEquity"),
        "a": {
            "configId": (cmp.get("a") or {}).get("config", {}).get("id"),
            "finalEquity": (cmp.get("a") or {}).get("finalEquity"),
            "tradeCount": (cmp.get("a") or {}).get("tradeCount"),
        },
        "b": {
            "configId": (cmp.get("b") or {}).get("config", {}).get("id"),
            "finalEquity": (cmp.get("b") or {}).get("finalEquity"),
            "tradeCount": (cmp.get("b") or {}).get("tradeCount"),
        },
        "panelSource": panel_source,
        "panelNote": panel_note,
        "compare": cmp,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": (
            "策略 A/B 旁路摘要（M-R5）；默认关闭；不替换主路径 picks；"
            "非投资建议；SIMULATE。"
        ),
    }


def attach_strategy_ab(
    brief: dict[str, Any],
    panel: pd.DataFrame,
    *,
    config_a: str | None = None,
    config_b: str | None = None,
    panel_source: str = "caller",
    panel_note: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Mutate brief with ``strategyAb`` key; return brief."""
    try:
        brief["strategyAb"] = run_strategy_ab_sidecar(
            panel,
            config_a=config_a,
            config_b=config_b,
            panel_source=panel_source,
            panel_note=panel_note,
            env=env,
        )
    except Exception as exc:  # noqa: BLE001 — sidecar must not break recommend
        brief["strategyAb"] = {
            "ok": False,
            "enabled": True,
            "error": f"{type(exc).__name__}: {exc}",
            "replacesPicks": False,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "note": "A/B 旁路失败（fail-visible）；主路径 picks 不受影响。",
        }
    return brief


# ---------------------------------------------------------------------------
# S1 — engine-backed A/B: two configs through the **same** portfolio engine.
# ---------------------------------------------------------------------------

# Metrics compared side by side. Every one is produced by the *same* portfolio
# layer (``portfolio.compute_metrics``) for both arms, so ``delta = B − A`` needs
# no re-normalisation (this is the A/B counterpart of the X4 rule).
AB_METRIC_KEYS = (
    "total_return",
    "cagr",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "win_rate",
    "n_trades",
    "avg_hold_days",
    "turnover_per_year",
    "turnover_notional_per_year",
    "avg_invested_ratio",
    "final_equity",
)


def _as_config(
    config: StrategyConfig | Mapping[str, Any] | str | Path,
) -> StrategyConfig:
    """Coerce a config id / packaged name / JSON path / mapping to a config.

    Bare ids are resolved with :func:`_resolve_config_ref`, so
    ``compare_strategy_ab_from_bars(bars, "lvrev-default-v1", ...)`` works the
    same way the daily-path sidecar resolves its packaged configs.
    """
    if isinstance(config, StrategyConfig):
        return config
    if isinstance(config, str):
        return load_strategy_config(_resolve_config_ref(config))
    return load_strategy_config(config)


def config_entry_provider(
    config: StrategyConfig | Mapping[str, Any] | str | Path,
) -> EntryProvider:
    """Build the screener entry provider a strategy config describes (``S1``).

    The provider screens with the config's ``weights`` / ``reversal_q`` /
    ``value_factor`` and applies the config's ``min_pick_score`` gate — but it runs
    **inside** the shared loop (:func:`book_replay.replay_book`), so it cannot
    bypass ``max_positions`` / the held-code filter / the limit seals / cooldown.
    """
    cfg = _as_config(config)
    return screener_entry_provider(
        reversal_q=cfg.reversal_q,
        min_pick_score=cfg.min_pick_score,
        value_factor=cfg.value_factor,
        weights=cfg.weights,
    )


def _review_block(
    trades: Any, open_positions: Any
) -> dict[str, Any]:
    """复盘 view of one arm — same ``看多收益>0 算对`` 口径 as ``performance``.

    ``settledCount`` = closed trades (T+N 已结算); ``pendingCount`` = positions
    still open at window end (未结算, not counted into accuracy). An empty book
    yields ``directionAccuracy=None`` — never a fabricated ``0``.
    """
    closed = list(trades or [])
    hits = sum(1 for t in closed if float(t.get("net_ret") or 0.0) > 0)
    settled = len(closed)
    return {
        "settledCount": settled,
        "pendingCount": len(list(open_positions or [])),
        "directionHits": hits,
        "directionAccuracy": (hits / settled) if settled else None,
        "metricNote": (
            "看多 Buy 净收益>0 算对（对齐 performance / U3 的 direction_accuracy 口径）；"
            "未平仓为 pending，不静默填 0。"
        ),
    }


def run_config_book(
    feats: pd.DataFrame,
    config: StrategyConfig | Mapping[str, Any] | str | Path,
    *,
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """Replay one strategy config through the shared loop (``S1``).

    ``feats`` is an already-built feature frame (see
    :func:`backtest.prepare_book_frame`); the config only supplies the entry
    provider. Returns the loop outputs plus ``metrics`` (portfolio single
    definition) and a 复盘 ``review`` block for the arm.
    """
    cfg = _as_config(config)
    loop = replay_book(feats, entry_provider=config_entry_provider(cfg), params=params)
    initial = (params or ReplayParams()).initial_capital
    return {
        "ok": True,
        "config": cfg.to_dict(),
        "equity_curve": loop["equity_curve"],
        "trades": loop["trades"],
        "open_positions": loop.get("open_positions") or [],
        "n_days": loop["n_days"],
        "final_equity": loop["final_equity"],
        "initial_capital": loop["initial_capital"],
        "metrics": compute_metrics(
            loop["equity_curve"], loop["trades"], initial_capital=initial
        ),
        "review": _review_block(loop["trades"], loop.get("open_positions")),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "disclaimer": "Research only; not investment advice.",
    }


def _delta_metrics(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, float | None]:
    """``delta = B − A`` for every comparable metric (``None`` when either is missing)."""
    out: dict[str, float | None] = {}
    for key in AB_METRIC_KEYS:
        av = a.get(key)
        bv = b.get(key)
        out[key] = (float(bv) - float(av)) if (av is not None and bv is not None) else None
    return out


def _pick_winner(a: Mapping[str, Any], b: Mapping[str, Any]) -> str:
    """Sharpe first (when both arms traded), else total return; ``"tie"`` otherwise."""
    id_a = str((a.get("config") or {}).get("id") or "A")
    id_b = str((b.get("config") or {}).get("id") or "B")
    m_a = a.get("metrics") or {}
    m_b = b.get("metrics") or {}
    if m_a.get("n_trades") and m_b.get("n_trades"):
        s_a = float(m_a.get("sharpe") or 0.0)
        s_b = float(m_b.get("sharpe") or 0.0)
        if s_a > s_b:
            return id_a
        if s_b > s_a:
            return id_b
    f_a = float(m_a.get("final_equity") or 0.0)
    f_b = float(m_b.get("final_equity") or 0.0)
    if f_a > f_b:
        return id_a
    if f_b > f_a:
        return id_b
    return "tie"


def _same_definition() -> dict[str, bool]:
    """Identity block proving both arms run the X4/B5 single definitions.

    ``backtest`` re-exports the shared loop / provider / metrics / exit function;
    asserting object identity here means an A/B run cannot silently diverge from
    the backtest — the exact ``B5`` / ``X4`` invariant, restated for the A/B.
    """
    from . import backtest as _backtest_mod
    from . import book_replay as _book_replay_mod
    from . import portfolio as _portfolio_mod
    from . import rules as _rules_mod

    return {
        "singleLoop": _backtest_mod.replay_book is _book_replay_mod.replay_book,
        "singleEntryProvider": (
            _backtest_mod.screener_entry_provider is _book_replay_mod.screener_entry_provider
        ),
        "singleMetrics": _backtest_mod.compute_metrics is _portfolio_mod.compute_metrics,
        "singleExitDefinition": _backtest_mod.evaluate_exit is _rules_mod.evaluate_exit,
    }


def compare_strategy_ab_engine(
    feats: pd.DataFrame,
    config_a: StrategyConfig | Mapping[str, Any] | str | Path,
    config_b: StrategyConfig | Mapping[str, Any] | str | Path,
    *,
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """Run two configs through the **same** engine and compare on one screen (``S1``).

    Both arms consume the *same* ``feats`` frame and the *same* ``replay_book``
    loop, so the only thing that differs between the two curves is the config. The
    payload carries full portfolio ``metrics`` + a 复盘 ``review`` block per arm,
    ``delta = B − A`` and a ``sameDefinition`` identity block.
    """
    a = run_config_book(feats, config_a, params=params)
    b = run_config_book(feats, config_b, params=params)
    out: dict[str, Any] = {
        "ok": True,
        "a": {
            "configId": (a.get("config") or {}).get("id"),
            "finalEquity": a.get("final_equity"),
            "tradeCount": len(a.get("trades") or []),
            "metrics": a.get("metrics"),
            "review": a.get("review"),
            "equityCurve": a.get("equity_curve"),
        },
        "b": {
            "configId": (b.get("config") or {}).get("id"),
            "finalEquity": b.get("final_equity"),
            "tradeCount": len(b.get("trades") or []),
            "metrics": b.get("metrics"),
            "review": b.get("review"),
            "equityCurve": b.get("equity_curve"),
        },
        "delta": _delta_metrics(a.get("metrics") or {}, b.get("metrics") or {}),
        "winner": _pick_winner(a, b),
        "sameDefinition": _same_definition(),
        "replacesPicks": False,
        "panelSource": "engine",
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "metricNote": (
            "两臂同一帧、同一引擎（book_replay 单点定义）；delta = B − A，同口径无需二次归一。"
        ),
        "disclaimer": (
            "策略 A/B 同源对照（研究指标）；非投资建议；SIMULATE；"
            "默认关闭；不替换主路径 picks。"
        ),
    }
    # A zero-trade arm neither took risk nor earned return; say so rather
    # than calling it a clean winner off the untouched initial capital.
    if not (out["a"]["metrics"] or {}).get("n_trades") or not (
        out["b"]["metrics"] or {}
    ).get("n_trades"):
        out["winnerNote"] = (
            "有一臂零成交，胜负仅供参考（零成交臂既未暴露风险也未产生收益）。"
        )
    return out


def compare_strategy_ab_from_bars(
    bars: pd.DataFrame,
    config_a: StrategyConfig | Mapping[str, Any] | str | Path,
    config_b: StrategyConfig | Mapping[str, Any] | str | Path,
    *,
    universe: str = "stock",
    start: str | None = None,
    end: str | None = None,
    pct_scale: str = "auto",
    params: ReplayParams | None = None,
) -> dict[str, Any]:
    """``bars`` → shared feature frame → engine A/B (CLI / API entry point).

    Fail-closed: an empty frame returns ``ok=False`` with a reason rather than two
    zero-filled curves.
    """
    feats = prepare_book_frame(
        bars, universe=universe, start=start, end=end, pct_scale=pct_scale
    )
    if feats.empty:
        return {
            "ok": False,
            "reason": "no bars in range",
            "universe": universe,
            "start": start,
            "end": end,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "disclaimer": "Research only; not investment advice.",
        }
    out = compare_strategy_ab_engine(feats, config_a, config_b, params=params)
    out["universe"] = universe
    out["start"] = start
    out["end"] = end
    return out
