"""Research brief routes — capability-matrix daily; SIMULATE product path."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from stock_platform_execution import ActivationBlocked, DraftBlocked, ProfileBlocked
from stock_platform_execution.timing import market_now
from stock_platform_providers import apply_adjust, get_market_strategy
from stock_platform_agents import AgentError, LlmUnavailableError, debate_brief_picks
from stock_platform_research import (
    UniverseEmptyError,
    brief_to_orders,
    build_premarket_brief,
    compare_strategy_configs,
    default_performance_log_path,
    default_universe_fixture_path,
    list_strategy_configs,
    log_brief_decisions,
    performance_summary,
    run_refresh,
)
from stock_platform_research.strategy_config import default_strategy_config_dir
import pandas as pd

from ..paper_ux import ensure_active_simulate_strategy, friendly_execution_detail
from ..state import CapabilityUnavailable

router = APIRouter(prefix="/api/research", tags=["research"])


def _parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None or not str(raw).strip():
        return None
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _optional_resolve(state: Any, capability: str) -> Any | None:
    try:
        return state.resolve(capability)
    except CapabilityUnavailable:
        return None


def _build_brief_for_request(
    request: Request,
    *,
    asof: date,
    symbols: list[str] | None,
    top_n: int,
    value_factor: bool,
    reversal_q: float,
    adjust_kind: str | None,
) -> dict[str, Any]:
    state = request.app.state.workbench
    daily = state.resolve("daily")
    adj = None
    adjust_fn = None
    kind = adjust_kind
    if kind:
        adj = _optional_resolve(state, "adj_factor")
        if adj is not None:
            adjust_fn = apply_adjust
        else:
            kind = None
    fund = _optional_resolve(state, "fund_flow")

    universe_path = None
    if symbols is None:
        packaged = default_universe_fixture_path()
        local = Path(state.fixtures_dir) / "universe_cn_sample.json"
        universe_path = local if local.is_file() else packaged

    try:
        return build_premarket_brief(
            asof=asof,
            symbols=symbols,
            universe_path=universe_path,
            daily_provider=daily,
            adj_provider=adj,
            fund_flow_provider=fund,
            apply_adjust_fn=adjust_fn,
            adjust_kind=kind,
            top_n=top_n,
            value_factor=value_factor,
            reversal_q=reversal_q,
        )
    except UniverseEmptyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/brief")
def get_brief(
    request: Request,
    asof: date = Query(..., description="Signal trade date (PIT as-of)"),
    symbols: str | None = Query(None, description="Comma-separated; default sample universe"),
    top_n: int = Query(10, ge=1, le=100, alias="topN"),
    value_factor: bool = Query(False, alias="valueFactor"),
    reversal_q: float = Query(0.30, alias="reversalQ"),
    adjust_kind: str | None = Query("qfq", description="qfq/hfq/none"),
) -> dict[str, Any]:
    kind = None if (adjust_kind or "").lower() in {"", "none", "raw"} else adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=asof,
        symbols=_parse_symbols(symbols),
        top_n=top_n,
        value_factor=value_factor,
        reversal_q=reversal_q,
        adjust_kind=kind,
    )
    daily = request.app.state.workbench.resolve("daily")
    brief["provider"] = getattr(daily, "name", type(daily).__name__)
    return brief


class BriefToPaperRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    qty: int = Field(100, ge=1, le=1_000_000)
    decision_only: bool = False
    now: str | None = None
    market: str = "CN"


@router.post("/brief/to-paper")
def brief_to_paper(request: Request, body: BriefToPaperRequest) -> dict[str, Any]:
    """Create a SIMULATE paper draft from brief TopN (auto-ensures default strategy)."""
    paper = request.app.state.workbench.paper
    try:
        ensured = ensure_active_simulate_strategy(paper.lifecycle)
    except ActivationBlocked as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc
    active = ensured["active"]

    kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=body.asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
    )
    orders = brief_to_orders(brief, qty=body.qty)
    mid = get_market_strategy(body.market).market_id
    if body.now:
        dt = datetime.fromisoformat(body.now.replace("Z", "+00:00"))
        now = market_now(mid, dt) if dt.tzinfo is None else dt
    else:
        now = market_now(mid)

    try:
        draft = paper.broker.build_draft(
            strategy_hash=str(active["strategyHash"]),
            signal_trade_date=body.asof.isoformat(),
            orders=orders,
            decision_only=body.decision_only,
            market=mid,
            now=now,
        )
    except (DraftBlocked, ProfileBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=friendly_execution_detail(exc)) from exc

    return {
        "brief": brief,
        "draft": draft,
        "broker": getattr(paper.broker, "name", "paper"),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "strategyAutoActivated": ensured["autoActivated"],
        "strategyStatus": ensured["statusMessage"],
    }

@router.post("/brief/to-broker")
def brief_to_broker(request: Request, body: BriefToPaperRequest) -> dict[str, Any]:
    """Alias of to-paper routed through resolve_broker (paper or ths_sim)."""
    return brief_to_paper(request, body)


class WizardDailyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(5, ge=1, le=100, alias="topN")
    adjust_kind: str | None = "none"
    qty: int = Field(100, ge=1, le=1_000_000)
    decision_only: bool = True
    now: str | None = "2026-09-07T09:40:00+08:00"
    market: str = "CN"
    skip_refresh: bool = Field(True, alias="skipRefresh")
    to_paper: bool = Field(True, alias="toPaper")


@router.post("/wizard/daily")
def wizard_daily(request: Request, body: WizardDailyRequest) -> dict[str, Any]:
    """One-click daily path: optional refresh → brief → paper draft (SIMULATE).

    Each step records ok/error; failures are visible and stop subsequent steps.
    Never enables live trading.
    """
    state = request.app.state.workbench
    steps: list[dict[str, Any]] = []
    symbols = _parse_symbols(body.symbols)

    # Step 1: refresh (local provider path; default skipped for thin UI demos)
    if body.skip_refresh:
        steps.append({"step": "refresh", "ok": True, "skipped": True})
    else:
        try:
            daily = state.resolve("daily")
            report = run_refresh(
                asof=body.asof,
                provider=daily,
                symbols=symbols or ["600519"],
                datasets=["daily"],
                max_attempts=1,
            )
            steps.append(
                {
                    "step": "refresh",
                    "ok": report.ok,
                    "skipped": False,
                    "failCount": report.to_dict().get("failCount"),
                }
            )
            if not report.ok:
                return {
                    "ok": False,
                    "steps": steps,
                    "environment": "SIMULATE",
                    "liveTradingEnabled": False,
                    "error": "refresh failed",
                }
        except CapabilityUnavailable as exc:
            steps.append({"step": "refresh", "ok": False, "error": str(exc)})
            return {
                "ok": False,
                "steps": steps,
                "environment": "SIMULATE",
                "liveTradingEnabled": False,
                "error": "refresh unavailable",
            }
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "refresh", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return {
                "ok": False,
                "steps": steps,
                "environment": "SIMULATE",
                "liveTradingEnabled": False,
                "error": "refresh error",
            }

    # Step 2: brief / recommend
    try:
        kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
        brief = _build_brief_for_request(
            request,
            asof=body.asof,
            symbols=symbols,
            top_n=body.top_n,
            value_factor=False,
            reversal_q=0.30,
            adjust_kind=kind,
        )
        steps.append(
            {
                "step": "brief",
                "ok": True,
                "pickCount": len(brief.get("picks") or []),
            }
        )
    except (HTTPException, CapabilityUnavailable) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        status = exc.status_code if isinstance(exc, HTTPException) else 409
        steps.append({"step": "brief", "ok": False, "error": detail})
        raise HTTPException(
            status_code=status,
            detail={"ok": False, "steps": steps, "error": detail, "liveTradingEnabled": False},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        steps.append({"step": "brief", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return {
            "ok": False,
            "steps": steps,
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "error": "brief failed",
        }

    draft = None
    if body.to_paper:
        paper_body = BriefToPaperRequest(
            asof=body.asof,
            symbols=body.symbols,
            topN=body.top_n,
            adjust_kind=body.adjust_kind,
            qty=body.qty,
            decision_only=body.decision_only,
            now=body.now,
            market=body.market,
        )
        strategy_auto = False
        strategy_status = None
        try:
            paper_out = brief_to_paper(request, paper_body)
            draft = paper_out.get("draft")
            strategy_auto = bool(paper_out.get("strategyAutoActivated"))
            strategy_status = paper_out.get("strategyStatus")
            steps.append(
                {
                    "step": "to_paper",
                    "ok": True,
                    "draftId": (draft or {}).get("draftId"),
                    "strategyAutoActivated": strategy_auto,
                    "strategyStatus": strategy_status,
                }
            )
        except HTTPException as exc:
            steps.append({"step": "to_paper", "ok": False, "error": exc.detail})
            return {
                "ok": False,
                "steps": steps,
                "brief": brief,
                "environment": "SIMULATE",
                "liveTradingEnabled": False,
                "error": "纸面草稿失败",
            }
    else:
        strategy_auto = False
        strategy_status = None
        steps.append({"step": "to_paper", "ok": True, "skipped": True})

    return {
        "ok": True,
        "steps": steps,
        "brief": brief,
        "draft": draft,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "strategyAutoActivated": strategy_auto,
        "strategyStatus": strategy_status,
        "disclaimer": "向导仅纸面 SIMULATE；非投资建议。",
    }

@router.get("/performance")
def get_performance(
    request: Request,
    log: str | None = Query(None, description="Optional JSONL path override"),
) -> dict[str, Any]:
    """Summarize settled recommend decisions (SIMULATE research metrics)."""
    import stock_platform_research

    path = Path(log) if log else default_performance_log_path()
    if not path.is_file():
        pkg_root = Path(stock_platform_research.__file__).resolve().parents[2]
        packaged = pkg_root / "tests" / "fixtures" / "recommend_decisions.jsonl"
        alt = Path(request.app.state.workbench.fixtures_dir) / "recommend_decisions.jsonl"
        if packaged.is_file():
            path = packaged
        elif alt.is_file():
            path = alt
    return performance_summary(path)


class LogBriefRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    holding: str = "5d"
    log: str | None = None


@router.post("/performance/log-brief")
def post_log_brief(request: Request, body: LogBriefRequest) -> dict[str, Any]:
    """Append pending TopN decisions from a brief into the performance JSONL."""
    kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=body.asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
    )
    path = Path(body.log) if body.log else default_performance_log_path()
    rows = log_brief_decisions(path, brief, holding=body.holding)
    return {
        "logPath": str(path),
        "appended": len(rows),
        "entries": rows,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


class BriefDebateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date
    symbols: str | None = None
    top_n: int = Field(5, ge=1, le=50, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    engine: str = "deterministic"
    max_picks: int | None = Field(None, ge=1, le=50, alias="maxPicks")


@router.post("/brief/debate")
def brief_debate(request: Request, body: BriefDebateRequest) -> dict[str, Any]:
    """Build TopN brief then run debate on picks (default deterministic; llm fail-closed)."""
    kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
    brief = _build_brief_for_request(
        request,
        asof=body.asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
    )
    daily = request.app.state.workbench.resolve("daily")
    brief["provider"] = getattr(daily, "name", type(daily).__name__)
    try:
        return debate_brief_picks(
            daily,
            brief,
            engine=body.engine,
            max_picks=body.max_picks,
        )
    except LlmUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AgentError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _fixture_compare_panel() -> pd.DataFrame:
    """Tiny deterministic panel for strategy compare when body omits rows."""
    rows = []
    for sym, closes, opens, vols, revs in [
        ("AAA", [10, 10.5, 11], [10, 10.2, 10.8], [0.1, 0.1, 0.1], [-0.1, -0.1, -0.1]),
        ("BBB", [20, 19, 18], [20, 19.5, 18.5], [0.5, 0.5, 0.5], [0.05, 0.05, 0.05]),
    ]:
        for i, d in enumerate(["2026-09-01", "2026-09-02", "2026-09-03"]):
            rows.append(
                {
                    "trade_date": d,
                    "symbol": sym,
                    "open": opens[i],
                    "close": closes[i],
                    "vol20": vols[i],
                    "rev_chg": revs[i],
                    "ma20": closes[i],
                    "ma60": closes[i] * 0.9,
                }
            )
    return pd.DataFrame(rows)


@router.get("/strategy/configs")
def get_strategy_configs() -> dict[str, Any]:
    return {
        "configs": list_strategy_configs(),
        "directory": str(default_strategy_config_dir()),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


class StrategyCompareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_a: str = Field(..., alias="configA", description="Config id or JSON path")
    config_b: str = Field(..., alias="configB")
    panel: list[dict[str, Any]] | None = None


def _resolve_config_ref(ref: str) -> Any:
    raw = ref.strip()
    root = default_strategy_config_dir()
    candidate = root / f"{raw}.json" if not raw.endswith(".json") else root / Path(raw).name
    if candidate.is_file():
        return candidate
    path = Path(raw)
    if path.is_file():
        return path
    # Allow bare id match
    for cfg in list_strategy_configs():
        if cfg["id"] == raw:
            return cfg["path"]
    raise HTTPException(status_code=404, detail=f"unknown strategy config: {ref}")


@router.post("/strategy/compare")
def post_strategy_compare(body: StrategyCompareRequest) -> dict[str, Any]:
    panel = pd.DataFrame(body.panel) if body.panel else _fixture_compare_panel()
    try:
        return compare_strategy_configs(
            panel,
            _resolve_config_ref(body.config_a),
            _resolve_config_ref(body.config_b),
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
