"""Research brief routes — capability-matrix daily; SIMULATE product path."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from stock_platform_execution import ActivationBlocked, DraftBlocked, ProfileBlocked
from stock_platform_execution.timing import market_now
from stock_platform_providers import get_market_strategy
from stock_platform_agents import AgentError, LlmUnavailableError, debate_brief_picks
from stock_platform_research import (
    UniverseEmptyError,
    brief_to_orders,
    compare_strategy_configs,
    default_performance_log_path,
    list_strategy_configs,
    log_brief_decisions,
    performance_summary,
    run_refresh,
)
from stock_platform_research.strategy_config import default_strategy_config_dir
import pandas as pd

from ..brief_ux import (
    build_brief_with_fallback,
    default_brief_asof,
    friendly_brief_error,
    paper_now_iso_for_asof,
    recommend_defaults,
)
from ..paper_ux import (
    ensure_active_simulate_strategy,
    friendly_execution_detail,
    is_upstream_transport_error,
)
from ..state import CapabilityUnavailable

router = APIRouter(prefix="/api/research", tags=["research"])


def _parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None or not str(raw).strip():
        return None
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _resolve_asof(request: Request, asof: date | None) -> date:
    if asof is not None:
        return asof
    return default_brief_asof(request.app.state.workbench)


def _build_brief_for_request(
    request: Request,
    *,
    asof: date | None,
    symbols: list[str] | None,
    top_n: int,
    value_factor: bool,
    reversal_q: float,
    adjust_kind: str | None,
    soft_gates: bool = True,
) -> dict[str, Any]:
    state = request.app.state.workbench
    try:
        return build_brief_with_fallback(
            state,
            asof=_resolve_asof(request, asof),
            symbols=symbols,
            top_n=top_n,
            value_factor=value_factor,
            reversal_q=reversal_q,
            adjust_kind=adjust_kind,
            soft_gates=soft_gates,
        )
    except UniverseEmptyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CapabilityUnavailable as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except Exception as exc:  # noqa: BLE001
        if is_upstream_transport_error(exc):
            raise HTTPException(status_code=503, detail=friendly_brief_error(exc)) from exc
        raise


@router.get("/defaults")
def get_recommend_defaults(request: Request) -> dict[str, Any]:
    """Default asof / symbols for wizard + recommend one-click path."""
    return recommend_defaults(request.app.state.workbench)


@router.get("/brief")
def get_brief(
    request: Request,
    asof: date | None = Query(None, description="Signal trade date; default last CN / fixture"),
    symbols: str | None = Query(None, description="Comma-separated; default sample universe"),
    top_n: int = Query(10, ge=1, le=100, alias="topN"),
    value_factor: bool = Query(False, alias="valueFactor"),
    reversal_q: float = Query(0.30, alias="reversalQ"),
    adjust_kind: str | None = Query("qfq", description="qfq/hfq/none"),
    soft_gates: bool = Query(True, alias="softGates"),
) -> dict[str, Any]:
    kind = None if (adjust_kind or "").lower() in {"", "none", "raw"} else adjust_kind
    return _build_brief_for_request(
        request,
        asof=asof,
        symbols=_parse_symbols(symbols),
        top_n=top_n,
        value_factor=value_factor,
        reversal_q=reversal_q,
        adjust_kind=kind,
        soft_gates=soft_gates,
    )


class BriefToPaperRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date | None = None
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    soft_gates: bool = Field(True, alias="softGates")
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
    asof = _resolve_asof(request, body.asof)
    brief = _build_brief_for_request(
        request,
        asof=asof,
        symbols=_parse_symbols(body.symbols),
        top_n=body.top_n,
        value_factor=body.value_factor,
        reversal_q=body.reversal_q,
        adjust_kind=kind,
        soft_gates=body.soft_gates,
    )
    orders = brief_to_orders(brief, qty=body.qty)
    mid = get_market_strategy(body.market).market_id
    if body.now:
        dt = datetime.fromisoformat(body.now.replace("Z", "+00:00"))
        now = market_now(mid, dt) if dt.tzinfo is None else dt
    else:
        now = market_now(mid, datetime.fromisoformat(paper_now_iso_for_asof(asof)))

    try:
        draft = paper.broker.build_draft(
            strategy_hash=str(active["strategyHash"]),
            signal_trade_date=asof.isoformat(),
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

    asof: date | None = None
    symbols: str | None = None
    top_n: int = Field(5, ge=1, le=100, alias="topN")
    adjust_kind: str | None = "none"
    soft_gates: bool = Field(True, alias="softGates")
    qty: int = Field(100, ge=1, le=1_000_000)
    decision_only: bool = True
    now: str | None = None
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
    asof = _resolve_asof(request, body.asof)
    now_iso = body.now or paper_now_iso_for_asof(asof)

    if body.skip_refresh:
        steps.append({"step": "refresh", "ok": True, "skipped": True})
    else:
        try:
            daily = state.resolve("daily")
            report = run_refresh(
                asof=asof,
                provider=daily,
                symbols=symbols or ["600519", "000001", "510300"],
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
            steps.append({"step": "refresh", "ok": False, "error": friendly_brief_error(exc)})
            return {
                "ok": False,
                "steps": steps,
                "environment": "SIMULATE",
                "liveTradingEnabled": False,
                "error": "refresh error",
            }

    try:
        kind = None if (body.adjust_kind or "").lower() in {"", "none", "raw"} else body.adjust_kind
        brief = _build_brief_for_request(
            request,
            asof=asof,
            symbols=symbols,
            top_n=body.top_n,
            value_factor=False,
            reversal_q=0.30,
            adjust_kind=kind,
            soft_gates=body.soft_gates,
        )
        steps.append(
            {
                "step": "brief",
                "ok": True,
                "pickCount": len(brief.get("picks") or []),
                "dataNote": brief.get("dataNote"),
                "gatesRelaxed": brief.get("gatesRelaxed"),
            }
        )
    except HTTPException as exc:
        detail = exc.detail
        steps.append({"step": "brief", "ok": False, "error": detail})
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "ok": False,
                "steps": steps,
                "error": detail,
                "liveTradingEnabled": False,
                "environment": "SIMULATE",
            },
        ) from exc
    except CapabilityUnavailable as exc:
        detail = exc.detail
        steps.append({"step": "brief", "ok": False, "error": detail})
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "steps": steps, "error": detail, "liveTradingEnabled": False},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        detail = friendly_brief_error(exc)
        steps.append({"step": "brief", "ok": False, "error": detail})
        if is_upstream_transport_error(exc):
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "steps": steps,
                    "error": detail,
                    "reason": "upstream_unavailable",
                    "environment": "SIMULATE",
                    "liveTradingEnabled": False,
                    "tip": "STOCK_PLATFORM_BRIEF_FALLBACK=replay",
                },
            ) from exc
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
            asof=asof,
            symbols=body.symbols,
            topN=body.top_n,
            adjust_kind=body.adjust_kind,
            softGates=body.soft_gates,
            qty=body.qty,
            decision_only=body.decision_only,
            now=now_iso,
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

    asof: date | None = None
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    soft_gates: bool = Field(True, alias="softGates")
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
        soft_gates=body.soft_gates,
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

    asof: date | None = None
    symbols: str | None = None
    top_n: int = Field(5, ge=1, le=50, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    soft_gates: bool = Field(True, alias="softGates")
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
        soft_gates=body.soft_gates,
    )
    daily = request.app.state.workbench.resolve("daily")
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
