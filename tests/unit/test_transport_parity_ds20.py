"""Unit tests for Transport Parity across CLI, REST, and MCP (§DS-20)."""

import json
import pytest
from typer.testing import CliRunner
from httpx import AsyncClient, ASGITransport

from scraper.cli.main import app as cli_app
from scraper.api.app import app as fastapi_app
from scraper.mcp.server import (
    deepsearch_crawl,
    deepsearch_inspect,
    deepsearch_capabilities,
    sanitize_archive_path,
)

runner = CliRunner()


def test_mcp_sanitize_archive_does_not_use_query():
    """Verify MCP archive sanitizer produces safe names without deriving filenames from arbitrary queries (§DS-20)."""
    p1 = sanitize_archive_path(None)
    p2 = sanitize_archive_path(None)
    assert p1 != p2  # Unique random ID
    assert p1.endswith(".zip")

    traversal = sanitize_archive_path("../../../evil.zip")
    assert "evil.zip" in traversal
    assert ".." not in traversal


def test_cli_invalid_mode_exit_code():
    """Verify CLI exits with code 2 on invalid execution mode."""
    result = runner.invoke(
        cli_app, ["crawl", "https://example.com", "--mode", "invalid_mode"]
    )
    assert result.exit_code == 2
    assert "Invalid mode" in result.stdout


@pytest.mark.asyncio
async def test_mcp_invalid_inputs_return_structured_errors():
    """Verify MCP tools return structured error JSON for invalid inputs."""
    res_empty_url = await deepsearch_crawl(url="")
    data = json.loads(res_empty_url)
    assert data["status"] == "failed"
    assert "empty" in data["error"].lower()

    res_invalid_mode = await deepsearch_crawl(
        url="https://example.com", mode="unsupported"
    )
    data_mode = json.loads(res_invalid_mode)
    assert data_mode["status"] == "failed"
    assert "invalid mode" in data_mode["error"].lower()


@pytest.mark.asyncio
async def test_rest_and_mcp_capabilities_parity():
    """Verify REST /capabilities and MCP deepsearch_capabilities return the exact same schema."""
    mcp_res = await deepsearch_capabilities()
    mcp_data = json.loads(mcp_res)
    assert mcp_data["status"] == "success"
    assert "capabilities" in mcp_data

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        rest_data = resp.json()
        assert rest_data["capabilities"].keys() == mcp_data["capabilities"].keys()


@pytest.mark.asyncio
async def test_rest_inspect_and_mcp_inspect_parity(monkeypatch):
    """Verify REST and MCP inspect tools return matching page intelligence keys."""
    from scraper.application.service import PageInspectionResult

    async def fake_inspect(self, url, mode=None):
        return PageInspectionResult(
            url=url,
            canonical_url=url,
            http_status=200,
            content_type="text/html",
            static_score=0.9,
            js_dependency_score=0.1,
            detected_apis_count=0,
            tables_count=1,
            canvas_detected=False,
            visual_score=0.0,
            recommended_strategy="HTTP",
            estimated_cost=1.0,
        )

    from scraper.application.service import DeepSearchService

    monkeypatch.setattr(DeepSearchService, "inspect", fake_inspect)

    # MCP
    mcp_res = await deepsearch_inspect("https://example.com/test")
    mcp_data = json.loads(mcp_res)
    assert mcp_data["status"] == "success"
    assert mcp_data["http_status"] == 200
    assert mcp_data["recommended_strategy"] == "HTTP"

    # REST
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/inspect",
            json={"url": "https://example.com/test"},
            headers={"X-API-Key": "dev-secret"},
        )
        assert resp.status_code == 200
        rest_data = resp.json()
        assert rest_data["http_status"] == 200
        assert rest_data["recommended_strategy"] == "HTTP"
