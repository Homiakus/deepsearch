"""Unit tests for Honest Minimal UI Dashboard (§DS-22)."""

import pytest
from httpx import AsyncClient, ASGITransport
from scraper.ui.dashboard import render_dashboard_html
from scraper.api.app import app as fastapi_app


def test_dashboard_html_offline_and_no_fake_metrics():
    """Verify rendered dashboard is self-contained with no external CDNs and no hardcoded static metrics."""
    html = render_dashboard_html()

    # Must not contain external Google Fonts or CDN scripts
    assert "fonts.googleapis.com" not in html
    assert "cdnjs.cloudflare.com" not in html
    assert "cdn.jsdelivr.net" not in html

    # Must not contain fake/fictitious metrics
    assert "Evidence Claims Stored" not in html
    assert "Qdrant Indexed" not in html
    assert "Autoscaling" not in html

    # Must contain essential truthful control plane elements
    assert "DeepSearch Platform Control Plane" in html
    assert "fetchHealth" in html
    assert "fetchCapabilities" in html
    assert "submitCrawl" in html
    assert "inspectUrl" in html


@pytest.mark.asyncio
async def test_dashboard_fastapi_route_serves_html():
    """Verify FastAPI GET / endpoint renders the truthful dashboard HTML."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "DeepSearch Platform Control Plane" in resp.text
