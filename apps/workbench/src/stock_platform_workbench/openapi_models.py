"""OpenAPI / Pydantic response envelopes for workbench HTTP APIs.

Models document stable top-level fields for `/docs` and contract tests.
Runtime handlers may return extra keys; prefer ``responses={200: {"model": ...}}``
over ``response_model=`` when the payload is intentionally open-ended, so FastAPI
does not strip fields.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtraAllowModel(BaseModel):
    """Base: documented fields + allow additional properties in schema."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ----- shared errors -----


class ErrorBody(ExtraAllowModel):
    """Generic error payload (HTTPException detail or handler content)."""

    reason: str | None = Field(None, description="Machine-readable reason code")
    detail: str | dict[str, Any] | None = Field(None, description="Human-readable or structured detail")
    liveTradingEnabled: bool = Field(False, description="Always false (M-E4 gate)")


class CapabilityUnavailableBody(ExtraAllowModel):
    """409 — matrix has no usable provider for the capability."""

    reason: str = Field(..., description="e.g. capability_unavailable")
    capability: str | None = None
    liveTradingEnabled: bool = False


class CircuitOpenBody(ExtraAllowModel):
    """503 — Eastmoney client circuit open."""

    reason: str = "eastmoney_circuit_open"
    detail: str | None = None
    liveTradingEnabled: bool = False


class UpstreamHttpErrorBody(ExtraAllowModel):
    """502 — requests transport failure."""

    reason: str = "upstream_http_error"
    error: str | None = None
    detail: str | None = None
    liveTradingEnabled: bool = False


class UpstreamTimeoutBody(ExtraAllowModel):
    """504 — upstream timeout."""

    reason: str = "upstream_timeout"
    detail: str | None = None
    liveTradingEnabled: bool = False


# Reusable OpenAPI response maps (merge per-route).
RESP_400: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorBody, "description": "Bad request / symbol / validation"},
}
RESP_404: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorBody, "description": "Not found"},
}
RESP_409: dict[int | str, dict[str, Any]] = {
    409: {"model": CapabilityUnavailableBody, "description": "Capability unavailable (fail-closed)"},
}
RESP_501: dict[int | str, dict[str, Any]] = {
    501: {"model": ErrorBody, "description": "Provider missing method"},
}
RESP_502: dict[int | str, dict[str, Any]] = {
    502: {"model": UpstreamHttpErrorBody, "description": "Upstream HTTP error"},
}
RESP_503: dict[int | str, dict[str, Any]] = {
    503: {"model": CircuitOpenBody, "description": "Service degraded / circuit / missing offline DB"},
}
RESP_504: dict[int | str, dict[str, Any]] = {
    504: {"model": UpstreamTimeoutBody, "description": "Upstream timeout"},
}

RESP_PROVIDER = {**RESP_400, **RESP_409, **RESP_501, **RESP_502, **RESP_503, **RESP_504}
RESP_RESEARCH = {**RESP_400, **RESP_409, **RESP_503, **RESP_502, **RESP_504}


# ----- meta / ops -----


class HealthResponse(ExtraAllowModel):
    status: str = Field(..., description="ok")
    service: str = Field(..., description="workbench")
    version: str


class VersionResponse(ExtraAllowModel):
    version: str


class OpsHealthResponse(ExtraAllowModel):
    status: str = Field(..., description="ok | degraded")
    service: str
    version: str
    liveTradingEnabled: bool = False
    executionMode: str = Field("SIMULATE", description="Always SIMULATE")
    defaultReplay: bool
    providerPreset: str | None = None
    briefFallback: str | None = None
    supplementTokenConfigured: bool = False
    preferences: dict[str, str] = Field(default_factory=dict)
    eastmoney: dict[str, Any] = Field(default_factory=dict)
    lastRefresh: dict[str, Any] | None = None


# ----- settings -----


class CapabilityMatrixRow(ExtraAllowModel):
    id: str
    usable: bool
    effective: str | None = None
    candidates: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)


class PreferencesResponse(ExtraAllowModel):
    preferences: dict[str, str]


class PreferencesPutResponse(ExtraAllowModel):
    preferences: dict[str, str]
    matrix: list[CapabilityMatrixRow]


class PresetsListResponse(ExtraAllowModel):
    default: str
    startup: str
    presets: list[dict[str, Any]]


class PresetApplyResponse(ExtraAllowModel):
    applied: str
    isDefault: bool = False
    preferences: dict[str, str]
    matrix: list[CapabilityMatrixRow]
    note: str | None = None
    liveTradingEnabled: bool = False


# ----- market -----


class MarketRowsResponse(ExtraAllowModel):
    capability: str
    provider: str
    rows: list[dict[str, Any]] = Field(default_factory=list)


class MarketItemsResponse(ExtraAllowModel):
    capability: str
    provider: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class MarketMinuteResponse(MarketRowsResponse):
    freq: str = "1m"


class MarketAdjFactorResponse(MarketRowsResponse):
    kind: str = "qfq"


class MarketFullMinuteResponse(MarketRowsResponse):
    trade_date: str | None = None
    count: int = 300


class MarketDailyAdjustedResponse(ExtraAllowModel):
    capabilities: list[str]
    providers: dict[str, str]
    kind: str
    rows: list[dict[str, Any]] = Field(default_factory=list)


# ----- paper / broker -----


class PaperStatusResponse(ExtraAllowModel):
    liveTradingEnabled: bool = False
    environment: str | None = "SIMULATE"
    banner: str | None = None
    lifecycle: dict[str, Any] = Field(default_factory=dict)
    admission: dict[str, Any] = Field(default_factory=dict)


class StrategyEnsureDefaultResponse(ExtraAllowModel):
    active: dict[str, Any]
    strategyHash: str | None = None
    strategyAutoActivated: bool = False
    strategyStatus: str | None = None
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False


class PaperDraftResponse(ExtraAllowModel):
    draftId: str | None = None
    executionEligible: bool | None = None
    strategyAutoActivated: bool | None = None
    strategyStatus: str | None = None
    liveTradingEnabled: bool = False


class PaperExecuteResponse(ExtraAllowModel):
    accepted: bool | None = None
    idempotentReplay: bool | None = None
    draftId: str | None = None
    executionId: str | None = None
    environment: str | None = "SIMULATE"
    liveTradingEnabled: bool = False


class BrokerStatusResponse(ExtraAllowModel):
    broker: str | None = None
    liveTradingEnabled: bool = False
    environment: str = "SIMULATE"
    positions: list[dict[str, Any]] = Field(default_factory=list)
    account: dict[str, Any] = Field(default_factory=dict)
    admission: dict[str, Any] = Field(default_factory=dict)
    gated: bool | None = None
    hint: str | None = None


# ----- agents -----


class AgentReportResponse(ExtraAllowModel):
    symbol: str | None = None
    asof: str | None = None
    environment: str | None = None
    liveTradingEnabled: bool | None = False


class DebateStatusResponse(ExtraAllowModel):
    available: bool | None = None
    engine: str | None = None
    deepGraph: dict[str, Any] | None = None


# ----- research -----


class RecommendDefaultsResponse(ExtraAllowModel):
    asof: str | None = None
    symbols: list[str] | str | None = None
    universeTier: str | None = None
    strategyAb: dict[str, Any] | None = None
    liveTradingEnabled: bool | None = False


class BriefResponse(ExtraAllowModel):
    asof: str
    market: str | None = "CN"
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    provider: str | None = None
    picks: list[dict[str, Any]] = Field(default_factory=list)
    persistOk: bool | None = None
    persisted: bool | None = None


class BriefListResponse(ExtraAllowModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    emptyMessage: str | None = None


class BriefSaveResponse(ExtraAllowModel):
    ok: bool = True
    asof: str
    updatedAt: str | None = None
    pickCount: int = 0
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    note: str | None = None


class BriefReviewResponse(ExtraAllowModel):
    asof: str
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list)
    direction_accuracy: float | None = None
    directionAccuracy: float | None = None


class BriefToPaperResponse(ExtraAllowModel):
    brief: dict[str, Any]
    draft: dict[str, Any] | None = None
    broker: str | None = None
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    strategyAutoActivated: bool | None = None
    strategyStatus: str | None = None


class WizardDailyResponse(ExtraAllowModel):
    ok: bool
    steps: list[dict[str, Any]] = Field(default_factory=list)
    brief: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    strategyAutoActivated: bool | None = None
    strategyStatus: str | None = None
    disclaimer: str | None = None
    error: str | None = None


class PerformanceSummaryResponse(ExtraAllowModel):
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    settledCount: int | None = None
    pendingCount: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metricDefinitions: dict[str, Any] | None = None
    settleSource: str | None = None
    settledNewly: int | None = None
    autoSettled: bool | None = None


class LogBriefResponse(ExtraAllowModel):
    logPath: str
    appended: int
    entries: list[dict[str, Any]] = Field(default_factory=list)
    fromStore: bool = False
    asof: str | None = None
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    note: str | None = None


class StrategyConfigsResponse(ExtraAllowModel):
    configs: list[dict[str, Any]] = Field(default_factory=list)
    directory: str | None = None
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False


class StrategyAbStatusResponse(ExtraAllowModel):
    enabled: bool | None = None
    note: str | None = None
    environment: str | None = "SIMULATE"
    liveTradingEnabled: bool = False


class StrategyCompareResponse(ExtraAllowModel):
    panelSource: str | None = None
    panelRows: int | None = None
    panelDates: int | None = None
    lastN: int | None = None
    universeTier: str | None = None
    panelNote: str | None = None
    environment: str | None = None
    liveTradingEnabled: bool | None = False


class WalkForwardResponse(ExtraAllowModel):
    ok: bool | None = None
    folds: list[dict[str, Any]] | None = None
    environment: str | None = "SIMULATE"
    liveTradingEnabled: bool | None = False


class FactorIcResponse(ExtraAllowModel):
    ok: bool | None = None
    rank_ic: float | None = None
    icir: float | None = None
    environment: str | None = None
    liveTradingEnabled: bool | None = False


class RollingBacktestResponse(ExtraAllowModel):
    ok: bool = True
    days: list[dict[str, Any]] = Field(default_factory=list)
    environment: str | None = "SIMULATE"
    liveTradingEnabled: bool | None = False


class PitFundamentalsResponse(ExtraAllowModel):
    ok: bool = True
    offlinePit: bool = True
    dataNote: str | None = "offline_pit"
    table: str
    asof: str
    provider: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    environment: str = "SIMULATE"
    liveTradingEnabled: bool = False
    note: str | None = None


def ok200(model: type[BaseModel], description: str = "OK") -> dict[int | str, dict[str, Any]]:
    """Build a 200 response entry for OpenAPI."""
    return {200: {"model": model, "description": description}}
