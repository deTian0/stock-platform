"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stock_platform_providers import CircuitOpenError, SymbolError

from . import __version__
from .openapi_models import (
    CircuitOpenBody,
    ErrorBody,
    UpstreamHttpErrorBody,
    UpstreamTimeoutBody,
)
from .routes import agents, broker, market, meta, ops, paper, research, settings
from .state import CapabilityUnavailable, WorkbenchState, build_default_state

_PKG_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PKG_DIR / "templates"))


def _try_request_exception() -> type[BaseException] | None:
    try:
        from requests.exceptions import RequestException

        return RequestException
    except ImportError:  # pragma: no cover
        return None


def create_app(
    *,
    fixtures_dir: Path | None = None,
    state: WorkbenchState | None = None,
) -> FastAPI:
    app = FastAPI(
        title="stock-platform workbench",
        version=__version__,
        description=(
            "量化研究工作台 HTTP API。\n\n"
            "- 行情经能力矩阵 `resolve(capability)`，禁止品牌硬编码。\n"
            "- 交易永远 **SIMULATE**（`liveTradingEnabled=false`）；不提供实盘开关（M-E4）。\n"
            "- 交互文档：`/docs`（Swagger）、`/redoc`、`/openapi.json`。\n"
            "- CI / 本地契约测请设 `STOCK_PLATFORM_PROVIDER_PRESET=replay`（零公网）。"
        ),
        contact={"name": "stock-platform"},
        license_info={"name": "LicenseRef-Pending"},
    )

    if state is None:
        if fixtures_dir is None:
            fixtures_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
        state = build_default_state(fixtures_dir)

    app.state.workbench = state

    @app.exception_handler(CapabilityUnavailable)
    async def _capability_unavailable(_request: Request, exc: CapabilityUnavailable) -> JSONResponse:
        return JSONResponse(status_code=409, content=exc.detail)

    @app.exception_handler(CircuitOpenError)
    async def _circuit_open(_request: Request, exc: CircuitOpenError) -> JSONResponse:
        body = CircuitOpenBody(detail=str(exc))
        return JSONResponse(status_code=503, content=body.model_dump())

    @app.exception_handler(SymbolError)
    async def _symbol_error(_request: Request, exc: SymbolError) -> JSONResponse:
        body = ErrorBody(reason="symbol_error", detail=str(exc))
        return JSONResponse(status_code=400, content=body.model_dump())

    _ReqExc = _try_request_exception()
    if _ReqExc is not None:

        @app.exception_handler(_ReqExc)
        async def _upstream_http(_request: Request, exc: BaseException) -> JSONResponse:
            body = UpstreamHttpErrorBody(error=type(exc).__name__, detail=str(exc))
            return JSONResponse(status_code=502, content=body.model_dump())

    @app.exception_handler(TimeoutError)
    async def _timeout(_request: Request, exc: TimeoutError) -> JSONResponse:
        body = UpstreamTimeoutBody(detail=str(exc))
        return JSONResponse(status_code=504, content=body.model_dump())

    app.mount(
        "/static",
        StaticFiles(directory=str(_PKG_DIR / "static")),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"version": __version__},
        )

    app.include_router(meta.router)
    app.include_router(ops.router)
    app.include_router(settings.router)
    app.include_router(market.router)
    app.include_router(agents.router)
    app.include_router(paper.router)
    app.include_router(broker.router)
    app.include_router(research.router)
    return app
