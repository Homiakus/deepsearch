"""Unit tests for FastAPI REST API endpoints (§55, §57)."""

import pytest
from fastapi.testclient import TestClient
from scraper.api.app import create_app

client = TestClient(create_app())


def test_api_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_api_inspect():
    res = client.post("/api/v1/inspect", json={"url": "https://example.com"})
    assert res.status_code == 200
    data = res.json()
    assert "recommended_strategy" in data
    assert data["canonical_url"] == "https://example.com/"


def test_api_search():
    res = client.post("/api/v1/search/hybrid", json={"query": "test query", "limit": 5})
    assert res.status_code == 200
    results = res.json()
    assert len(results) > 0


def test_ui_dashboard_endpoint():
    res = client.get("/ui")
    assert res.status_code == 200
    assert "DeepSearch Platform" in res.text
