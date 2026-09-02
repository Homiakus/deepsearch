"""Unit tests for FastAPI REST API endpoints, Auth, CORS, and Path Traversal Prevention (§55, §57, §DS-08)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.api.app import create_app
from scraper.config import settings

client = TestClient(create_app())
AUTH_HEADERS = {"X-API-Key": settings.api_key}


def test_api_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_unauthenticated_request_rejected():
    """Verify protected endpoints reject requests without API key (§DS-08)."""
    res = client.post("/api/v1/search/hybrid", json={"query": "test", "limit": 5})
    assert res.status_code == 401


def test_invalid_api_key_rejected():
    """Verify protected endpoints reject invalid API keys with 403 (§DS-08)."""
    res = client.post(
        "/api/v1/search/hybrid",
        headers={"X-API-Key": "wrong-secret-key"},
        json={"query": "test", "limit": 5},
    )
    assert res.status_code == 403


def test_bearer_token_authentication_accepted():
    """Verify Bearer token authorization header is accepted (§DS-08)."""
    with patch("scraper.config.settings.experimental_search", True):
        res = client.post(
            "/api/v1/search/hybrid",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json={"query": "test", "limit": 5},
        )
        assert res.status_code == 200


def test_api_inspect():
    mock_pi = PageIntelligence(
        content_type="text/html",
        static_score=0.9,
        js_dependency_score=0.1,
        content_quality=0.95,
    )
    mock_artifact = CapturedArtifact(
        url="https://example.com",
        canonical_url="https://example.com/",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"<html><body><h1>Test</h1></body></html>",
        text_content="<html><body><h1>Test</h1></body></html>",
        page_intelligence=mock_pi,
    )
    with patch(
        "scraper.acquisition.engine.AdaptiveAcquisitionEngine.acquire_page",
        new_callable=AsyncMock,
    ) as mock_acquire:
        mock_acquire.return_value = mock_artifact
        res = client.post(
            "/api/v1/inspect",
            headers=AUTH_HEADERS,
            json={"url": "https://example.com"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "recommended_strategy" in data
        assert data["canonical_url"] == "https://example.com/"


def test_api_search_stable_returns_501_and_experimental_returns_200():
    # In stable profile (default), search is disabled -> 501
    res = client.post(
        "/api/v1/search/hybrid",
        headers=AUTH_HEADERS,
        json={"query": "test query", "limit": 5},
    )
    assert res.status_code == 501
    detail = res.json().get("detail", {})
    assert detail.get("error") == "capability_unavailable"
    assert detail.get("capability") == "hybrid_search"

    # When experimental_search is explicitly enabled -> 200
    with patch("scraper.config.settings.experimental_search", True):
        res_exp = client.post(
            "/api/v1/search/hybrid",
            headers=AUTH_HEADERS,
            json={"query": "test query", "limit": 5},
        )
        assert res_exp.status_code == 200
        results = res_exp.json()
        assert isinstance(results, list)


def test_api_search_query_detailed():
    with patch("scraper.config.settings.experimental_search", True):
        res = client.post(
            "/api/v1/search/query",
            headers=AUTH_HEADERS,
            json={"query": "test query", "limit": 5},
        )
        assert res.status_code == 200
        data = res.json()
        assert "state" in data
        assert "results" in data


def test_ui_dashboard_endpoint():
    res = client.get("/ui")
    assert res.status_code == 200
    assert "DeepSearch Platform" in res.text


def test_api_capabilities_endpoint():
    res = client.get("/api/v1/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "capabilities" in data
    assert "research_pipeline" in data["capabilities"]
    assert data["capabilities"]["research_pipeline"]["status"] == "stable"
    assert data["capabilities"]["hybrid_search"]["status"] == "disabled"
    assert data["capabilities"]["pixel_rag"]["status"] == "disabled"


def test_disabled_endpoint_returns_501():
    res = client.post(
        "/api/v1/search/visual",
        headers=AUTH_HEADERS,
        json={"query": "test query", "limit": 5},
    )
    assert res.status_code == 501
    detail = res.json().get("detail", {})
    assert detail.get("error") == "capability_unavailable"
    assert detail.get("capability") == "pixel_rag"
    assert detail.get("status") == "disabled"


def test_cors_policy_headers():
    """Verify CORS headers respond to allowed origins and reject wildcard with credentials (§DS-08)."""
    # Allowed origin
    res = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Disallowed origin
    res_disallowed = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://malicious-site.evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in res_disallowed.headers
