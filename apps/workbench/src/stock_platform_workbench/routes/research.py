"""Research brief routes — capability-matrix daily; SIMULATE product path."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from stock_platform_execution import ActivationBlocked, DraftBlocked, ProfileBlocked
from stock_platform_execution.timing import market_now
from stock_platform_providers import get_market_strategy
from stock_platform_agents import AgentError, LlmUnavailableError, debate_brief_picks
from stock_platform_research import (
    UniverseEmptyError,
    attach_strategy_ab,
    brief_to_orders,
    build_multi_day_pit_panel,
    compare_strategy_configs,
    default_performance_log_path,
    list_strategy_configs,
    log_brief_decisions,
    open_brief_repository,
    performance_summary,
    review_stored_brief,
    run_refresh,
    run_rolling_recommend_review,
    settle_performance_log,
    strategy_ab_enabled,
    strategy_ab_status,
    summarize_factor_ic,
    summarize_factor_ic_from_rows,
    summarize_walk_forward,
)
from stock_platform_research.rolling_review import resolve_asof_window, resolve_universe_symbols
from stock_platform_research.strategy_config import default_strategy_config_dir
import pandas as pd

from ..brief_ux import (
    build_brief_with_fallback,
    default_brief_asof,
    friendly_brief_error,
    paper_now_iso_for_asof,
    recommend_defaults,
)
from ..intel_report_ux import (
    build_crosswalk,
    list_kinds,
    prefill_intel_report,
)
from ..openapi_models import (
    RESP_400,
    RESP_404,
    RESP_RESEARCH,
    RESP_503,
    BriefListResponse,
    BriefResponse,
    BriefReviewResponse,
    BriefSaveResponse,
    BriefToPaperResponse,
    FactorIcResponse,
    IntelReportCrosswalkResponse,
    IntelReportPrefillResponse,
    LogBriefResponse,
    PerformanceSummaryResponse,
    PitFundamentalsResponse,
    RecommendDefaultsResponse,
    RollingBacktestResponse,
    StrategyAbStatusResponse,
    StrategyCompareResponse,
    StrategyConfigsResponse,
    WalkForwardResponse,
    WizardDailyResponse,
    ok200,
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


def _brief_repo(request: Request):
    """Resolve shared brief repository (tests may set state.brief_repo)."""
    state = request.app.state.workbench
    override = getattr(state, "brief_repo", None)
    if override is not None:
        return override
    return open_brief_repository()


def _log_brief_to_performance(brief: dict[str, Any], *, holding: str = "5d") -> None:
    """Append pending decisions after persist; never raise into recommend path."""
    try:
        path = default_performance_log_path()
        appended = log_brief_decisions(path, brief, holding=holding, skip_existing=True)
        brief["perfLogOk"] = True
        brief["perfLogAppended"] = len(appended)
        brief["perfLogPath"] = str(path)
        brief["perfLogHolding"] = holding
        if appended:
            brief["perfLogNote"] = f"已记入绩效样本 {len(appended)} 条（pending；同日同码跳过）"
        else:
            brief["perfLogNote"] = "绩效样本已存在或无 picks，未追加"
    except Exception as exc:  # noqa: BLE001 — recommend must stay usable
        brief["perfLogOk"] = False
        brief["perfLogAppended"] = 0
        brief["perfLogError"] = f"推荐已落库，但记入绩效失败：{type(exc).__name__}: {exc}"


def _persist_brief(
    request: Request,
    brief: dict[str, Any],
    *,
    symbols: list[str] | None = None,
    log_performance: bool = True,
) -> dict[str, Any]:
    """Upsert brief; annotate response with persistOk / Chinese errors."""
    try:
        record = _brief_repo(request).save(brief, symbols=symbols)
        brief["persisted"] = True
        brief["persistOk"] = True
        brief["persistedAt"] = record.updated_at
        brief["persistAsOf"] = record.asof
        if log_performance and brief.get("picks"):
            _log_brief_to_performance(brief)
        return brief
    except Exception as exc:  # noqa: BLE001 — keep recommend usable if DB fails
        brief["persisted"] = False
        brief["persistOk"] = False
        brief["persistError"] = f"推荐已生成，但落库失败：{type(exc).__name__}: {exc}"
        return brief


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
    universe_tier: str | None = None,
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
            universe_tier=universe_tier,
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


@router.get(
    "/defaults",
    summary="推荐默认参数",
    responses=ok200(RecommendDefaultsResponse),
)
def get_recommend_defaults(
    request: Request,
    universe_tier: str | None = Query(
        None,
        alias="universeTier",
        description="core|watch|full — default watch (not full market)",
    ),
) -> dict[str, Any]:
    """Default asof / symbols for wizard + recommend one-click path."""
    out = recommend_defaults(request.app.state.workbench, universe_tier=universe_tier)
    out["strategyAb"] = strategy_ab_status()
    return out


def _maybe_attach_strategy_ab(
    request: Request,
    brief: dict[str, Any],
    *,
    request_flag: bool,
    symbols: list[str] | None,
    universe_tier: str | None,
) -> dict[str, Any]:
    """Attach A/B sidecar when env or request flag opts in (never replaces picks)."""
    if not strategy_ab_enabled(request_flag=request_flag):
        brief.setdefault(
            "strategyAb",
            {
                "ok": True,
                "enabled": False,
                "replacesPicks": False,
                "note": strategy_ab_status()["note"],
                "environment": "SIMULATE",
                "liveTradingEnabled": False,
            },
        )
        return brief
    panel, eng_source, eng_err = _engine_compare_panel(
        request,
        last_n=8,
        universe_tier=universe_tier or "core",
        symbols=symbols,
    )
    if panel is None:
        panel = _fixture_compare_panel()
        return attach_strategy_ab(
            brief,
            panel,
            panel_source="fixture",
            panel_note=eng_err or "无 engine/daily 面板，回退演示 fixture（不冒充 live）",
        )
    return attach_strategy_ab(
        brief,
        panel,
        panel_source=eng_source or "engine_sqlite",
        panel_note=None,
    )


@router.get(
    "/brief",
    summary="盘前 TopN 推荐",
    responses={**ok200(BriefResponse), **RESP_RESEARCH},
)
def get_brief(
    request: Request,
    asof: date | None = Query(None, description="Signal trade date; default last CN / fixture"),
    symbols: str | None = Query(None, description="Comma-separated; default sample universe"),
    top_n: int = Query(10, ge=1, le=100, alias="topN", description="Top N picks"),
    value_factor: bool = Query(False, alias="valueFactor", description="Enable value factor"),
    reversal_q: float = Query(0.30, alias="reversalQ", description="Reversal quantile"),
    adjust_kind: str | None = Query("qfq", description="qfq/hfq/none"),
    soft_gates: bool = Query(True, alias="softGates", description="Relax hard gates when needed"),
    persist: bool = Query(True, description="Auto-save to SQLite archive (U2)"),
    universe_tier: str | None = Query(
        "watch",
        alias="universeTier",
        description="When symbols empty: core|watch|full (default watch)",
    ),
    strategy_ab: bool = Query(
        False,
        alias="strategyAb",
        description="Opt-in A/B sidecar (or set STOCK_PLATFORM_STRATEGY_AB=1); default off",
    ),
) -> dict[str, Any]:
    """Build premarket brief; default auto-persists to SQLite and logs pending performance."""
    kind = None if (adjust_kind or "").lower() in {"", "none", "raw"} else adjust_kind
    syms = _parse_symbols(symbols)
    brief = _build_brief_for_request(
        request,
        asof=asof,
        symbols=syms,
        top_n=top_n,
        value_factor=value_factor,
        reversal_q=reversal_q,
        adjust_kind=kind,
        soft_gates=soft_gates,
        universe_tier=universe_tier,
    )
    _maybe_attach_strategy_ab(
        request,
        brief,
        request_flag=strategy_ab,
        symbols=syms,
        universe_tier=universe_tier,
    )
    if persist:
        _persist_brief(request, brief, symbols=syms)
    return brief


@router.get(
    "/briefs",
    summary="历史推荐列表",
    responses=ok200(BriefListResponse),
)
def list_briefs(
    request: Request,
    limit: int = Query(30, ge=1, le=365, description="Max recent rows"),
) -> dict[str, Any]:
    """List recent persisted briefs (summary rows; Chinese UI)."""
    rows = _brief_repo(request).list_recent(limit=limit)
    return {
        "items": [r.summary_dict() for r in rows],
        "count": len(rows),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "emptyMessage": None if rows else "暂无已保存的推荐。生成今日推荐后会自动落库。",
    }


@router.get(
    "/briefs/{asof}",
    summary="按日回看已存推荐",
    responses={**ok200(BriefResponse), **RESP_404},
)
def get_stored_brief(request: Request, asof: date) -> dict[str, Any]:
    """Load one archived brief by asof (404 + Chinese detail when missing)."""
    record = _brief_repo(request).get_by_asof(asof.isoformat())
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 asof={asof.isoformat()} 的已存推荐（请先生成并落库）",
        )
    body = record.to_dict()
    # Prefer full payload for UI replay of cards/table.
    if record.payload:
        merged = dict(record.payload)
        merged.update(
            {
                "persisted": True,
                "persistOk": True,
                "persistedAt": record.updated_at,
                "persistAsOf": record.asof,
                "stored": body,
            }
        )
        return merged
    return body


def _load_brief_readonly(request: Request, asof: date | None) -> dict[str, Any] | None:
    """Read archived brief only — never persist / never write WebSearch into SQLite."""
    if asof is None:
        return None
    record = _brief_repo(request).get_by_asof(asof.isoformat())
    if record is None:
        return None
    if record.payload and isinstance(record.payload, dict):
        return dict(record.payload)
    return record.to_dict()


def _ops_snapshot_for_intel(request: Request) -> dict[str, Any]:
    from stock_platform_workbench import __version__
    from stock_platform_workbench.brief_ux import ops_data_visibility

    vis = ops_data_visibility()
    return {
        "status": "ok",
        "version": __version__,
        "providerPreset": vis.get("providerPreset"),
        "briefFallback": vis.get("briefFallback"),
        "liveTradingEnabled": False,
        "executionMode": "SIMULATE",
    }


def _try_concept_items(request: Request, symbols: list[str]) -> list[dict[str, Any]] | None:
    if not symbols:
        return None
    state = request.app.state.workbench
    try:
        provider = state.resolve("concept_blocks")
    except CapabilityUnavailable:
        return None
    getter = getattr(provider, "get_concept_blocks", None)
    if getter is None:
        return None
    try:
        items = getter(symbols[:8])
    except Exception:  # noqa: BLE001 — prefill stays usable without concepts
        return None
    return items if isinstance(items, list) else None


@router.get(
    "/intel-report/crosswalk",
    summary="情报报告 ↔ brief 对照（只读）",
    responses={**ok200(IntelReportCrosswalkResponse), **RESP_400},
)
def intel_report_crosswalk(
    request: Request,
    asof: date | None = Query(None, description="截面日；默认取最近默认 asof"),
) -> dict[str, Any]:
    """MR-3: asof/宇宙对照；不写 brief SQLite；不跑 Skill。"""
    asof_d = asof or default_brief_asof()
    brief = _load_brief_readonly(request, asof_d)
    walk = build_crosswalk(asof=asof_d, brief=brief)
    walk.update(
        {
            "kinds": list_kinds(),
            "writesBriefSqlite": False,
            "liveTradingEnabled": False,
            "environment": "SIMULATE",
            "emptyMessage": None
            if brief
            else f"同日 asof={asof_d.isoformat()} 无已存 brief；请先在今日推荐/向导生成（对照空态，不造假）",
        }
    )
    return walk


@router.get(
    "/intel-report/prefill",
    summary="用平台数据预填情报模板预览",
    responses={**ok200(IntelReportPrefillResponse), **RESP_400, **RESP_404},
)
def intel_report_prefill(
    request: Request,
    kind: str = Query(
        "a-share-preopen",
        description="a-share-preopen | a-share-intraday | us-preopen",
    ),
    asof: date | None = Query(None, description="截面日；用于日历与 brief 对照"),
    fmt: str = Query("json", alias="format", description="json | html（html 直接预览）"),
) -> Any:
    """MR-5: partial fill from brief/ops/concept_blocks; never writes brief SQLite."""
    asof_d = asof or default_brief_asof()
    brief = _load_brief_readonly(request, asof_d)
    picks = (brief or {}).get("picks") or []
    symbols = [
        str(p.get("symbol"))
        for p in picks
        if isinstance(p, dict) and p.get("symbol")
    ]
    concept_items = _try_concept_items(request, symbols)
    ops = _ops_snapshot_for_intel(request)
    try:
        payload = prefill_intel_report(
            kind=kind,
            asof=asof_d,
            brief=brief,
            ops_health=ops,
            concept_items=concept_items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if (fmt or "json").lower() == "html":
        return HTMLResponse(content=payload["html"], media_type="text/html; charset=utf-8")
    return payload


@router.post(
    "/briefs",
    summary="显式保存推荐",
    responses={**ok200(BriefSaveResponse), **RESP_400},
)
def post_save_brief(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Explicit save of a brief payload (same upsert-by-asof semantics)."""
    if not body.get("asof"):
        raise HTTPException(status_code=400, detail="缺少 asof，无法保存推荐")
    if "picks" not in body:
        raise HTTPException(status_code=400, detail="缺少 picks，无法保存推荐")
    if not body.get("environment"):
        body = {**body, "environment": "SIMULATE"}
    symbols = body.get("symbols")
    sym_list: list[str] | None
    if isinstance(symbols, str):
        sym_list = _parse_symbols(symbols)
    elif isinstance(symbols, list):
        sym_list = [str(s).strip() for s in symbols if str(s).strip()]
    else:
        sym_list = None
    record = _brief_repo(request).save(body, symbols=sym_list)
    return {
        "ok": True,
        "asof": record.asof,
        "updatedAt": record.updated_at,
        "pickCount": len(record.picks),
        "environment": record.environment,
        "liveTradingEnabled": False,
        "note": "同日重复保存会覆盖该 asof 的权威存档（幂等 upsert）。",
    }


@router.get(
    "/briefs/{asof}/review",
    summary="已存推荐 T+N 复盘",
    responses={**ok200(BriefReviewResponse), **RESP_404},
)
def review_brief(
    request: Request,
    asof: date,
    holding: str = Query("1d", description="Holding window, e.g. 1d / 5d"),
) -> dict[str, Any]:
    """U3 skeleton: T+N mark for a stored brief (pending when bars missing)."""
    record = _brief_repo(request).get_by_asof(asof.isoformat())
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 asof={asof.isoformat()} 的已存推荐，无法复盘",
        )
    get_daily = None
    try:
        daily = request.app.state.workbench.resolve("daily")

        def _gd(symbols: list[str], *, start: date, end: date) -> list[dict[str, Any]]:
            return list(daily.get_daily(symbols, start=start, end=end) or [])

        get_daily = _gd
    except CapabilityUnavailable:
        get_daily = None
    payload = record.to_dict()
    return review_stored_brief(payload, get_daily=get_daily, holding=holding)


class BriefToPaperRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date | None = Field(None, description="Signal trade date")
    symbols: str | None = Field(None, description="Comma-separated tickers")
    top_n: int = Field(10, ge=1, le=100, alias="topN", description="Top N picks")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = Field("qfq", description="qfq/hfq/none")
    soft_gates: bool = Field(True, alias="softGates")
    universe_tier: str | None = Field("watch", alias="universeTier")
    qty: int = Field(100, ge=1, le=1_000_000, description="Order qty per pick")
    decision_only: bool = Field(False, description="Decision-only draft (no fill)")
    now: str | None = Field(None, description="Clock override ISO-8601")
    market: str = Field("CN", description="Market id")


@router.post(
    "/brief/to-paper",
    summary="推荐 → 纸面草稿",
    responses={**ok200(BriefToPaperResponse), **RESP_RESEARCH},
)
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
        universe_tier=body.universe_tier,
    )
    _persist_brief(request, brief, symbols=_parse_symbols(body.symbols))
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


@router.post(
    "/brief/to-broker",
    summary="推荐 → 券商草稿（别名）",
    responses={**ok200(BriefToPaperResponse), **RESP_RESEARCH},
)
def brief_to_broker(request: Request, body: BriefToPaperRequest) -> dict[str, Any]:
    """Alias of to-paper routed through resolve_broker (paper or ths_sim)."""
    return brief_to_paper(request, body)


class WizardDailyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date | None = Field(None, description="Signal trade date")
    symbols: str | None = Field(None, description="Comma-separated tickers")
    top_n: int = Field(5, ge=1, le=100, alias="topN")
    adjust_kind: str | None = Field("none", description="qfq/hfq/none")
    soft_gates: bool = Field(True, alias="softGates")
    universe_tier: str | None = Field("watch", alias="universeTier")
    qty: int = Field(100, ge=1, le=1_000_000)
    decision_only: bool = Field(True, description="Default decision-only for wizard")
    now: str | None = None
    market: str = "CN"
    skip_refresh: bool = Field(True, alias="skipRefresh", description="Skip refresh step")
    to_paper: bool = Field(True, alias="toPaper", description="Create paper draft after brief")


@router.post(
    "/wizard/daily",
    summary="日用向导（refresh→brief→paper）",
    responses={**ok200(WizardDailyResponse), **RESP_RESEARCH},
)
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
            universe_tier=body.universe_tier,
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
        _maybe_attach_strategy_ab(
            request,
            brief,
            request_flag=False,
            symbols=symbols,
            universe_tier=body.universe_tier,
        )
        _persist_brief(request, brief, symbols=symbols)
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
            universeTier=body.universe_tier,
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


def _settle_get_daily(request: Request):
    """Prefer engine_sqlite (offline market.db) for settle; else active daily."""
    state = request.app.state.workbench
    engine = state.providers.get("engine_sqlite")
    if engine is not None:

        def _gd_engine(symbols: list[str], *, start: date, end: date) -> list[dict[str, Any]]:
            return list(engine.get_daily(symbols, start=start, end=end) or [])

        return _gd_engine, "engine_sqlite"
    try:
        daily = state.resolve("daily")

        def _gd(symbols: list[str], *, start: date, end: date) -> list[dict[str, Any]]:
            return list(daily.get_daily(symbols, start=start, end=end) or [])

        return _gd, getattr(daily, "name", "daily")
    except CapabilityUnavailable:
        return None, None


@router.get(
    "/performance",
    summary="绩效汇总",
    responses=ok200(PerformanceSummaryResponse),
)
def get_performance(
    request: Request,
    log: str | None = Query(None, description="Optional JSONL path override"),
    auto_settle: bool = Query(
        True,
        alias="autoSettle",
        description="When true, settle pending rows with enough subsequent bars into JSONL",
    ),
    recent_days: int = Query(
        5,
        ge=1,
        le=30,
        alias="recentDays",
        description="How many latest settled dates to include in recentDays[]",
    ),
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

    settle_source = None
    if auto_settle and path.is_file():
        get_daily, settle_source = _settle_get_daily(request)
        if get_daily is not None:
            summary = settle_performance_log(
                path, get_daily=get_daily, recent_days=recent_days
            )
            summary["settleSource"] = settle_source
            return summary

    summary = performance_summary(path, recent_days=recent_days)
    summary["settledNewly"] = 0
    summary["autoSettled"] = False
    summary["settleSource"] = settle_source
    return summary


@router.post(
    "/performance/settle",
    summary="显式结算 pending 绩效",
    responses={**ok200(PerformanceSummaryResponse), **RESP_404, **RESP_503},
)
def post_settle_performance(
    request: Request,
    log: str | None = Query(None, description="Optional JSONL path override"),
) -> dict[str, Any]:
    """Explicitly settle pending JSONL rows using engine_sqlite or active daily."""
    path = Path(log) if log else default_performance_log_path()
    get_daily, settle_source = _settle_get_daily(request)
    if get_daily is None:
        raise HTTPException(
            status_code=503,
            detail="无可用日线源，无法结算 pending（可配置 STOCK_PLATFORM_ENGINE_MARKET_DB）",
        )
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"绩效日志不存在：{path}")
    summary = settle_performance_log(path, get_daily=get_daily)
    summary["settleSource"] = settle_source
    return summary


class LogBriefRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asof: date | None = Field(None, description="Signal date")
    symbols: str | None = None
    top_n: int = Field(10, ge=1, le=100, alias="topN")
    value_factor: bool = Field(False, alias="valueFactor")
    reversal_q: float = Field(0.30, alias="reversalQ")
    adjust_kind: str | None = "qfq"
    soft_gates: bool = Field(True, alias="softGates")
    holding: str = Field("5d", description="Holding window label")
    log: str | None = Field(None, description="JSONL path override")
    from_store: bool = Field(
        False,
        alias="fromStore",
        description="If true, load archived brief by asof instead of regenerating",
    )


@router.post(
    "/performance/log-brief",
    summary="将推荐记入绩效 JSONL",
    responses={**ok200(LogBriefResponse), **RESP_400, **RESP_404},
)
def post_log_brief(request: Request, body: LogBriefRequest) -> dict[str, Any]:
    """Append pending TopN decisions from a brief into the performance JSONL."""
    path = Path(body.log) if body.log else default_performance_log_path()
    if body.from_store:
        if body.asof is None:
            raise HTTPException(status_code=400, detail="fromStore 需要 asof")
        record = _brief_repo(request).get_by_asof(body.asof.isoformat())
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"未找到 asof={body.asof.isoformat()} 的已存推荐，无法记入绩效",
            )
        brief = record.to_dict()
    else:
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
    rows = log_brief_decisions(path, brief, holding=body.holding, skip_existing=True)
    return {
        "logPath": str(path),
        "appended": len(rows),
        "entries": rows,
        "fromStore": bool(body.from_store),
        "asof": brief.get("asof"),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": "同 asof+symbol 已存在则跳过（幂等）",
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
    universe_tier: str | None = Field("watch", alias="universeTier")
    engine: str = Field("deterministic", description="deterministic | llm")
    max_picks: int | None = Field(None, ge=1, le=50, alias="maxPicks")


@router.post(
    "/brief/debate",
    summary="推荐 picks 辩论",
    responses={**ok200(BriefResponse), **RESP_RESEARCH},
)
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
        universe_tier=body.universe_tier,
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


@router.get(
    "/strategy/configs",
    summary="策略配置列表",
    responses=ok200(StrategyConfigsResponse),
)
def get_strategy_configs() -> dict[str, Any]:
    """List packaged strategy JSON configs for A/B compare."""
    return {
        "configs": list_strategy_configs(),
        "directory": str(default_strategy_config_dir()),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
    }


@router.get(
    "/strategy/ab-status",
    summary="策略 A/B 旁路状态",
    responses=ok200(StrategyAbStatusResponse),
)
def get_strategy_ab_status() -> dict[str, Any]:
    """M-R5: whether daily-path A/B sidecar is opted in (default off)."""
    return strategy_ab_status()


class StrategyCompareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_a: str = Field(..., alias="configA", description="Config id or JSON path")
    config_b: str = Field(..., alias="configB", description="Config id or JSON path")
    panel: list[dict[str, Any]] | None = Field(None, description="Optional PIT panel rows")
    last_n: int = Field(8, ge=2, le=20, alias="lastN")
    universe_tier: str = Field("core", alias="universeTier")
    symbols: str | None = None
    require_engine: bool = Field(
        False,
        alias="requireEngine",
        description="When true, fail-closed 503 if no engine/daily panel (no fixture)",
    )


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


def _engine_compare_panel(
    request: Request,
    *,
    last_n: int,
    universe_tier: str,
    symbols: list[str] | None,
) -> tuple[pd.DataFrame | None, str | None, str | None]:
    """Build multi-day PIT panel from engine/daily; return (panel, source, error)."""
    get_daily, source = _settle_get_daily(request)
    if get_daily is None:
        return None, None, "无可用日线源（engine market.db / daily）"
    try:
        univ, tier, _guidance = resolve_universe_symbols(
            symbols=symbols,
            universe_tier=universe_tier or "core",
        )
        # Soft cap for interactive compare (not full-market).
        if len(univ) > 40:
            univ = univ[:40]
        asofs = resolve_asof_window(get_daily, last_n=last_n)
        if len(asofs) < 2:
            return None, source, "交易日不足 2 日，无法做 PIT 对比"
        panel = build_multi_day_pit_panel(
            asof_dates=asofs,
            symbols=univ,
            get_daily=get_daily,
            lookback_calendar_days=120,
        )
        if panel.empty or panel["trade_date"].nunique() < 2:
            return None, source, "engine 面板为空或交易日不足（检查 market.db 覆盖）"
        return panel, source or "engine_sqlite", None
    except (UniverseEmptyError, ValueError, FileNotFoundError, OSError, KeyError) as exc:
        return None, source, str(exc)
    except Exception as exc:  # noqa: BLE001 — compare must not 500; fall back fixture
        return None, source, f"{type(exc).__name__}: {exc}"


@router.post(
    "/strategy/compare",
    summary="策略配置对比",
    responses={**ok200(StrategyCompareResponse), **RESP_400, **RESP_404, **RESP_503},
)
def post_strategy_compare(request: Request, body: StrategyCompareRequest) -> dict[str, Any]:
    """Compare two strategy configs on engine/daily panel or fixture."""
    panel_source = "body"
    panel_note = None
    if body.panel:
        panel = pd.DataFrame(body.panel)
    else:
        panel, eng_source, eng_err = _engine_compare_panel(
            request,
            last_n=body.last_n,
            universe_tier=body.universe_tier or "core",
            symbols=_parse_symbols(body.symbols),
        )
        if panel is not None:
            panel_source = eng_source or "engine_sqlite"
        elif body.require_engine:
            raise HTTPException(
                status_code=503,
                detail=(
                    (eng_err or "无法构建 engine 面板")
                    + "。请配置 STOCK_PLATFORM_ENGINE_MARKET_DB（只读），"
                    "或去掉 requireEngine 以使用演示 fixture（不冒充 live）。"
                ),
            )
        else:
            panel = _fixture_compare_panel()
            panel_source = "fixture"
            panel_note = (
                (eng_err + "；") if eng_err else ""
            ) + "已回退内置演示面板（非 live；研究对比用）"

    try:
        out = compare_strategy_configs(
            panel,
            _resolve_config_ref(body.config_a),
            _resolve_config_ref(body.config_b),
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    out["panelSource"] = panel_source
    out["panelRows"] = int(len(panel))
    out["panelDates"] = int(panel["trade_date"].nunique()) if "trade_date" in panel.columns else 0
    out["lastN"] = body.last_n
    out["universeTier"] = body.universe_tier
    if panel_note:
        out["panelNote"] = panel_note
    return out


class RollingBacktestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    last_n: int | None = Field(5, ge=1, le=20, alias="lastN")
    asof_start: date | None = Field(None, alias="asofStart")
    asof_end: date | None = Field(None, alias="asofEnd")
    symbols: str | None = None
    universe_tier: str | None = Field("watch", alias="universeTier")
    holding: str = Field("1d", description="Holding window")
    top_n: int = Field(5, ge=1, le=20, alias="topN")
    soft_gates: bool = Field(True, alias="softGates")


@router.post(
    "/backtest/rolling-review",
    summary="滚动推荐复盘回测",
    responses={**ok200(RollingBacktestResponse), **RESP_400, **RESP_503},
)
def post_rolling_backtest(request: Request, body: RollingBacktestRequest) -> dict[str, Any]:
    """U7 light: roll recommend + review_stored_brief on engine/daily (SIMULATE)."""
    get_daily, source = _settle_get_daily(request)
    if get_daily is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "无可用日线源，无法回测。请配置 STOCK_PLATFORM_ENGINE_MARKET_DB "
                "指向 a-stock-engine/data_cache/market.db（只读），或启用含 daily 的预设。"
            ),
        )
    out = run_rolling_recommend_review(
        get_daily=get_daily,
        symbols=_parse_symbols(body.symbols),
        universe_tier=body.universe_tier or "watch",
        asof_start=body.asof_start,
        asof_end=body.asof_end,
        last_n=body.last_n if body.asof_start is None else None,
        holding=body.holding,
        top_n=body.top_n,
        soft_gates=body.soft_gates,
        daily_source=source,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "回测失败")
    return out


class WalkForwardRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: date = Field(..., description="Window start YYYY-MM-DD")
    end: date = Field(..., description="Window end YYYY-MM-DD")
    train_days: int = Field(60, ge=1, le=500, alias="trainDays")
    test_days: int = Field(20, ge=1, le=120, alias="testDays")
    step_days: int = Field(20, ge=1, le=120, alias="stepDays")
    fold_records: list[dict[str, Any]] | None = Field(None, alias="foldRecords")
    objective: str = Field("total_return", description="OOS objective key")
    direction: str = Field("max", description="max | min")


@router.post(
    "/backtest/walk-forward",
    summary="Walk-forward 折叠摘要",
    responses={**ok200(WalkForwardResponse), **RESP_400},
)
def post_walk_forward(body: WalkForwardRequest) -> dict[str, Any]:
    """M-R2: walk-forward fold plan + optional OOS summary (not daily brief path)."""
    try:
        return summarize_walk_forward(
            start=body.start,
            end=body.end,
            train_days=body.train_days,
            test_days=body.test_days,
            step_days=body.step_days,
            fold_records=body.fold_records,
            objective=body.objective,
            direction=body.direction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class FactorIcRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    observations: list[dict[str, Any]] | None = Field(None, description="Pre-aggregated IC observations")
    rows: list[dict[str, Any]] | None = Field(None, description="Raw factor/return rows")
    factor_key: str = Field("factor", alias="factorKey")
    return_key: str = Field("forward_return", alias="returnKey")


@router.post(
    "/backtest/factor-ic",
    summary="因子 Rank IC / ICIR",
    responses={**ok200(FactorIcResponse), **RESP_400},
)
def post_factor_ic(body: FactorIcRequest) -> dict[str, Any]:
    """M-R4 deep: rank IC / ICIR summary (not on lvrev / brief path)."""
    if body.observations:
        return summarize_factor_ic(
            body.observations,
            factor_key=body.factor_key,
            return_key=body.return_key,
        )
    if body.rows:
        return summarize_factor_ic_from_rows(
            body.rows,
            factor_key=body.factor_key,
            return_key=body.return_key,
        )
    raise HTTPException(status_code=400, detail="需要 observations 或 rows")


@router.get(
    "/pit/fundamentals",
    summary="离线 PIT 基本面",
    responses={**ok200(PitFundamentalsResponse), **RESP_400, **RESP_503},
)
def get_pit_fundamentals(
    request: Request,
    symbols: str = Query(..., description="Comma-separated CN tickers"),
    asof: date = Query(..., description="PIT cutoff YYYY-MM-DD"),
    kind: str = Query(
        "fundamentals",
        description="fundamentals (ann_date<=asof) or daily_basic (trade_date=asof)",
    ),
) -> dict[str, Any]:
    """ADR 0050 offline PIT helpers via engine_sqlite (fail-closed; not live financial)."""
    from stock_platform_providers.engine_sqlite import (
        MSG_DB_MISSING,
        EngineSqliteProvider,
        resolve_engine_market_db,
    )

    if resolve_engine_market_db() is None:
        raise HTTPException(status_code=503, detail=MSG_DB_MISSING)
    try:
        provider = EngineSqliteProvider()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    try:
        if kind in {"daily_basic", "daily_basic_pit", "basic"}:
            rows = provider.get_daily_basic_pit(syms, asof=asof)
            table = "daily_basic_pit"
        else:
            rows = provider.get_fundamentals_pit(syms, asof=asof)
            table = "fundamentals_pit"
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "offlinePit": True,
        "dataNote": "offline_pit",
        "table": table,
        "asof": asof.isoformat(),
        "provider": provider.name,
        "rows": rows,
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "note": "非 live financial；与 brief SQLite 分离；禁止未来函数。",
    }
