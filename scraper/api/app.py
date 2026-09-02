"""FastAPI Application Entrypoint (§105, DS-A21, §DS-04)."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from scraper.config import settings
from scraper.application.service import get_deepsearch_service
from scraper.api.routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager controlling single DeepSearchService lifecycle (§DS-04)."""
    service = get_deepsearch_service()
    app.state.deepsearch_service = service
    try:
        yield
    finally:
        await service.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Adaptive Web Scraping & Retrieval Platform (§105, DS-A21)",
        lifespan=lifespan,
    )

    # Hardened CORS policy without wildcard credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    app.include_router(api_router)

    # Web UI Dashboard endpoint (§58, DS-22)
    @app.get("/", response_class=HTMLResponse)
    @app.get("/ui", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    async def get_ui_dashboard():
        from scraper.ui.dashboard import render_dashboard_html

        return render_dashboard_html()

    return app


app = create_app()
