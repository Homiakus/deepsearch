"""Unit tests for Epistemic REST API, MCP tool, and CLI commands (DS-40)."""

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from scraper.api.app import app as fastapi_app
from scraper.cli.main import app as cli_app
from scraper.config import settings
from scraper.mcp.server import deepsearch_epistemic_query

client = TestClient(fastapi_app)
runner = CliRunner()
AUTH_HEADERS = {"X-API-Key": settings.api_key or "deepsearch_secret_key"}


def test_api_epistemic_query():
    """Verify POST /api/v1/epistemic/query returns structured response."""
    payload = {
        "run_id": "api_test",
        "text": "What is deterministic evidence synthesis?",
        "intent": "factual",
    }
    response = client.post(
        "/api/v1/epistemic/query", json=payload, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "digest_sha256" in data
    assert "coverage" in data


def test_api_epistemic_ingest():
    """Verify POST /api/v1/epistemic/ingest ingests propositions."""
    payload = {
        "run_id": "api_test_ingest",
        "doc_id": "doc_1",
        "url": "https://example.com/sih",
        "nodes": [
            {
                "id": "claim:sih",
                "kind": "proposition",
                "text": "SNC delivers deterministic hallucination elimination.",
                "belief": 1.0,
            }
        ],
    }
    response = client.post(
        "/api/v1/epistemic/ingest", json=payload, headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("total_nodes") == 1


@pytest.mark.asyncio
async def test_mcp_epistemic_query_tool():
    """Verify deepsearch_epistemic_query FastMCP tool."""
    res_str = await deepsearch_epistemic_query(
        query="Verify state-based CRDT monotonicity",
        intent="factual",
    )
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert "digest_sha256" in res
    assert "artifact" in res


def test_cli_epistemic_commands():
    """Verify CLI scraper epistemic health and query commands."""
    res_health = runner.invoke(cli_app, ["epistemic", "health"])
    assert res_health.exit_code == 0
    assert "Epistemic Bridge" in res_health.stdout

    res_query = runner.invoke(
        cli_app, ["epistemic", "query", "Is deterministic consensus possible?"]
    )
    assert res_query.exit_code == 0
    assert "Epistemic Verification" in res_query.stdout
