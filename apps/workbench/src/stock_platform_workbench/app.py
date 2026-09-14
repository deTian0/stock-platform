"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .routes import agents, market, meta, paper, research, settings
from .state import CapabilityUnavailable, WorkbenchState, build_default_state

_PKG_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PKG_DIR / "templates"))


def create_app(
    *,
    fixtures_dir: Path | None = None,
    state: WorkbenchState | None = None,
) -> FastAPI:
    app = FastAPI(
        title="stock-platform workbench",
        version=__version__,
        description="Minimal research shell — routes resolve providers via capability matrix only.",
    )

    if state is None:
        if fixtures_dir is None:
            fixtures_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
        state = build_default_state(fixtures_dir)

    app.state.workbench = state

    @app.exception_handler(CapabilityUnavailable)
    async def _capability_unavailable(_request: Request, exc: CapabilityUnavailable) -> JSONResponse:
        return JSONResponse(status_code=409, content=exc.detail)

    app.mount(
        "/static",
        StaticFiles(directory=str(_PKG_DIR / "static")),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"version": __version__},
        )

    app.include_router(meta.router)
    app.include_router(settings.router)
    app.include_router(market.router)
    app.include_router(agents.router)
    app.include_router(paper.router)
    app.include_router(research.router)
    return app
