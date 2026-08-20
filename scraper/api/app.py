"""FastAPI Application Entrypoint (§105, DS-A21)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from scraper.config import settings
from scraper.api.routes import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Adaptive Web Scraping & Retrieval Platform (§105, DS-A21)",
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

    # Web UI Dashboard endpoint (§58)
    @app.get("/ui", response_class=HTMLResponse)
    async def get_ui_dashboard():
        from scraper.ui.dashboard import render_dashboard_html

        return render_dashboard_html()

    return app


app = create_app()
