"""Enterprise Production Conformance & Unit Tests for DeepSearch MCP Server.

Verifies protocol conformance, tool execution, path sanitization, cancellation propagation,
SSRF redirect protection, and error boundaries.
"""

import sys
import os
import json
import asyncio
import subprocess
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from scraper.acquisition.engine import CapturedArtifact, AdaptiveAcquisitionEngine
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.acquisition.http_fetcher import HTTPFetcher, SSRFValidationError
from scraper.config import ExecutionMode
from scraper.mcp.server import (
    deepsearch_inspect,
    deepsearch_extract,
    deepsearch_search,
    deepsearch_research,
    deepsearch_discover,
    sanitize_archive_path,
    mcp,
)
from scraper.application.research_service import research_service


@pytest.fixture(autouse=True)
def mock_network_acquisition():
    async def mock_acquire(
        url,
        canonical_url,
        mode=ExecutionMode.BALANCED,
        cached_content=None,
        take_screenshot=False,
    ):
        pi = PageIntelligence(
            content_type="text/html",
            static_score=0.85,
            js_dependency_score=0.15,
            content_quality=0.90,
        )
        fake_html = (
            f"<html><body><h1>Research Page for {url}</h1>"
            "<p>Machine learning, quantum algorithms, computing research, artificial intelligence models, "
            "and scientific algorithms documentation with comprehensive facts and citations.</p></body></html>"
        )
        return CapturedArtifact(
            url=url,
            canonical_url=canonical_url,
            strategy_used="L1_HTTP",
            status_code=200,
            content_type="text/html",
            raw_content=fake_html.encode("utf-8"),
            text_content=fake_html,
            page_intelligence=pi,
        )

    with (
        patch.object(
            AdaptiveAcquisitionEngine, "acquire_page", side_effect=mock_acquire
        ) as mock_acq,
        patch(
            "scraper.discovery.providers.registry.ProviderRegistry.search_parallel",
            new_callable=AsyncMock,
        ) as mock_search,
        patch(
            "scraper.pipeline.search_pipeline.fetch_wikimedia_topic_images",
            new_callable=AsyncMock,
        ) as mock_wm,
        patch(
            "scraper.pipeline.search_pipeline.fetch_wikipedia_article_images",
            new_callable=AsyncMock,
        ) as mock_wp,
        patch(
            "scraper.pipeline.search_pipeline.download_media_file",
            new_callable=AsyncMock,
        ) as mock_dm,
    ):
        mock_search.return_value = []
        mock_wm.return_value = []
        mock_wp.return_value = []
        mock_dm.return_value = None
        yield mock_acq


@pytest.mark.asyncio
async def test_mcp_tool_inspection():
    res_raw = await deepsearch_inspect("https://example.com/test")
    res = json.loads(res_raw)

    assert res["status"] == "success"
    assert res["url"] == "https://example.com/test"
    assert "http_status" in res
    assert "recommended_strategy" in res
    assert "static_score" in res


@pytest.mark.asyncio
async def test_mcp_tool_extraction():
    res_raw = await deepsearch_extract("https://example.com/test")
    res = json.loads(res_raw)

    assert res["status"] == "success"
    assert res["url"] == "https://example.com/test"
    assert "clean_markdown" in res
    assert "fit_markdown" in res


@pytest.mark.asyncio
async def test_mcp_tool_search():
    # In stable profile (default), search is unavailable
    res_raw_disabled = await deepsearch_search("quantum mechanics", limit=5)
    res_disabled = json.loads(res_raw_disabled)
    assert res_disabled["status"] == "unavailable"
    assert res_disabled["capability"] == "hybrid_search"

    # When experimental_search is explicitly enabled
    with patch("scraper.config.settings.experimental_search", True):
        res_raw = await deepsearch_search("quantum mechanics", limit=5)
        res = json.loads(res_raw)

        assert isinstance(res, dict)
        assert res["status"] == "success"
        assert "state" in res
        assert "results" in res
        assert isinstance(res["results"], list)


@pytest.mark.asyncio
async def test_mcp_tool_research():
    res_raw = await deepsearch_research(
        query="machine learning",
        domain="example.com",
        preferred_sources=["https://example.com/ml"],
        depth=1,
        max_pages=2,
        mode="fast",
        auto_discover=False,
    )
    res = json.loads(res_raw)

    assert res["status"] == "success"
    assert res["query"] == "machine learning"
    assert res["total_pages_processed"] > 0
    assert res["total_rag_chunks"] > 0
    assert "manifest" in res


@pytest.mark.asyncio
async def test_mcp_tool_research_with_category():
    res_raw = await deepsearch_research(
        query="quantum algorithms",
        preferred_sources=["https://example.com/qa"],
        depth=1,
        max_pages=1,
        mode="fast",
        category="science",
        auto_discover=False,
    )
    res = json.loads(res_raw)
    assert res["status"] == "success"


@pytest.mark.asyncio
async def test_mcp_tool_discover():
    with patch(
        "scraper.mcp.server.discover_diverse_seeds", new_callable=AsyncMock
    ) as mock_disc:
        mock_disc.return_value = ["https://arxiv.org/abs/2101.0001"]
        res_raw = await deepsearch_discover(
            query="quantum computing", category="science"
        )
        res = json.loads(res_raw)

        assert res["status"] == "success"
        assert res["query"] == "quantum computing"
        assert res["total_seeds"] == 1
        assert res["seeds"] == ["https://arxiv.org/abs/2101.0001"]


@pytest.mark.asyncio
async def test_mcp_tool_capabilities():
    from scraper.mcp.server import deepsearch_capabilities

    res_raw = await deepsearch_capabilities()
    res = json.loads(res_raw)
    assert res["status"] == "success"
    assert "capabilities" in res
    assert "research_pipeline" in res["capabilities"]
    assert res["capabilities"]["research_pipeline"]["status"] == "stable"
    assert res["capabilities"]["pixel_rag"]["status"] == "disabled"


def test_mcp_server_metadata():
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]

    assert "deepsearch_research" in tool_names
    assert "deepsearch_inspect" in tool_names
    assert "deepsearch_extract" in tool_names
    assert "deepsearch_search" in tool_names
    assert "deepsearch_discover" in tool_names
    assert "deepsearch_capabilities" in tool_names


# --- HARDENING & SECURITY TESTS ---


def test_sanitize_archive_path_traversal_protection():
    # Attempt directory traversal attacks
    p1 = sanitize_archive_path("../../etc/shadow.zip", "default.zip")
    assert ".." not in p1
    assert Path(p1).name == "shadow.zip"

    p2 = sanitize_archive_path("C:\\Windows\\System32\\malicious.zip", "default.zip")
    assert Path(p2).name == "malicious.zip"
    assert Path(p2).parent == Path.cwd()

    p3 = sanitize_archive_path(None, "default_test.zip")
    assert "default_test.zip" in p3


@pytest.mark.asyncio
async def test_mcp_research_empty_query():
    res_raw = await deepsearch_research(query="   ")
    res = json.loads(res_raw)
    assert res["status"] == "failed"
    assert "Query parameter cannot be empty" in res["error"]


@pytest.mark.asyncio
async def test_mcp_inspect_error_handling():
    with patch.object(
        AdaptiveAcquisitionEngine,
        "acquire_page",
        side_effect=RuntimeError("DNS resolution failed"),
    ):
        res_raw = await deepsearch_inspect("https://unreachable-domain.com")
        res = json.loads(res_raw)
        assert res["status"] == "failed"
        assert "DNS resolution failed" in res["error"]


@pytest.mark.asyncio
async def test_mcp_extract_error_handling():
    with patch.object(
        AdaptiveAcquisitionEngine,
        "acquire_page",
        side_effect=RuntimeError("Connection reset by peer"),
    ):
        res_raw = await deepsearch_extract("https://broken-domain.com")
        res = json.loads(res_raw)
        assert res["status"] == "failed"
        assert "Connection reset by peer" in res["error"]


@pytest.mark.asyncio
async def test_mcp_search_empty_query():
    res_raw = await deepsearch_search(query="")
    res = json.loads(res_raw)
    assert res["status"] == "failed"
    assert "Query parameter cannot be empty" in res["error"]


@pytest.mark.asyncio
async def test_mcp_research_cancellation_propagation():
    # Start research and cancel during execution
    cancel_mock = AsyncMock()
    with patch.object(research_service, "cancel", cancel_mock):
        task = asyncio.create_task(
            deepsearch_research(
                query="test cancellation topic",
                depth=1,
                max_pages=1,
                mode="fast",
                auto_discover=False,
            )
        )
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Verify research_service.cancel was invoked
        assert cancel_mock.called


def test_ssrf_validation_blocks_private_ips():
    # Direct loopback
    with pytest.raises(SSRFValidationError):
        HTTPFetcher.validate_url_security("http://127.0.0.1:8080/secret")

    # AWS metadata IP
    with pytest.raises(SSRFValidationError):
        HTTPFetcher.validate_url_security("http://169.254.169.254/latest/meta-data/")

    # IPv6 localhost
    with pytest.raises(SSRFValidationError):
        HTTPFetcher.validate_url_security("http://[::1]/admin")


def test_stdio_jsonrpc_handshake_e2e():
    """Runs a full JSON-RPC 2.0 stdio handshake to verify MCP protocol compliance."""
    workspace_root = Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace_root)

    proc = subprocess.Popen(
        [sys.executable, "-m", "scraper.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(workspace_root),
        env=env,
        text=True,
    )

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest-mcp-e2e", "version": "1.0.0"},
        },
    }
    initialized_notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    list_tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

    try:
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.write(json.dumps(initialized_notification) + "\n")
        proc.stdin.write(json.dumps(list_tools_req) + "\n")
        proc.stdin.flush()

        tools_found = []
        server_info = {}

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("id") == 1:
                    server_info = msg.get("result", {}).get("serverInfo", {})
                elif msg.get("id") == 2:
                    tools_list = msg.get("result", {}).get("tools", [])
                    tools_found = [t.get("name") for t in tools_list]
                    break
            except json.JSONDecodeError:
                continue

        proc.terminate()
        proc.wait(timeout=3)

        assert server_info.get("name") == "deepsearch"
        assert "deepsearch_research" in tools_found
        assert "deepsearch_inspect" in tools_found
        assert "deepsearch_extract" in tools_found
        assert "deepsearch_search" in tools_found
        assert "deepsearch_discover" in tools_found
        assert "deepsearch_capabilities" in tools_found

    finally:
        if proc.poll() is None:
            proc.kill()
