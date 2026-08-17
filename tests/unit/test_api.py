"""Unit tests for FastAPI REST API endpoints (§55, §57)."""

import pytest
from fastapi.testclient import TestClient
from scraper.api.app import create_app

client = TestClient(create_app())


def test_api_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


from unittest.mock import AsyncMock, patch
from scraper.acquisition.engine import CapturedArtifact
from scraper.acquisition.page_classifier import PageIntelligence


def test_api_inspect():
    mock_pi = PageIntelligence(
        content_type="text/html",
        static_score=0.9,
        js_dependency_score=0.1,
        content_quality=0.95
    )
    mock_artifact = CapturedArtifact(
        url="https://example.com",
        canonical_url="https://example.com/",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"<html><body><h1>Test</h1></body></html>",
        text_content="<html><body><h1>Test</h1></body></html>",
        page_intelligence=mock_pi
    )
    with patch("scraper.api.routes.acquisition_engine.acquire_page", new_callable=AsyncMock) as mock_acquire:
        mock_acquire.return_value = mock_artifact
        res = client.post("/api/v1/inspect", json={"url": "https://example.com"})
        assert res.status_code == 200
        data = res.json()
        assert "recommended_strategy" in data
        assert data["canonical_url"] == "https://example.com/"


def test_api_search():
    res = client.post("/api/v1/search/hybrid", json={"query": "test query", "limit": 5})
    assert res.status_code == 200
    results = res.json()
    assert isinstance(results, list)

def test_api_search_query_detailed():
    res = client.post("/api/v1/search/query", json={"query": "test query", "limit": 5})
    assert res.status_code == 200
    data = res.json()
    assert "state" in data
    assert "results" in data


def test_ui_dashboard_endpoint():
    res = client.get("/ui")
    assert res.status_code == 200
    assert "DeepSearch Platform" in res.text
