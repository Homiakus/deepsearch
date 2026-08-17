"""Unit tests for DeepSearch MCP Server."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from scraper.acquisition.engine import CapturedArtifact, AdaptiveAcquisitionEngine
from scraper.acquisition.page_classifier import PageIntelligence
from scraper.config import ExecutionMode
from scraper.mcp.server import (
    deepsearch_inspect,
    deepsearch_extract,
    deepsearch_search,
    deepsearch_research,
    deepsearch_discover,
    mcp
)


@pytest.fixture(autouse=True)
def mock_network_acquisition():
    async def mock_acquire(url, canonical_url, mode=ExecutionMode.BALANCED, cached_content=None, take_screenshot=False):
        pi = PageIntelligence(
            content_type="text/html",
            static_score=0.85,
            js_dependency_score=0.15,
            content_quality=0.90
        )
        fake_html = f"<html><body><h1>Research Page for {url}</h1><p>Machine learning, quantum algorithms, computing research, artificial intelligence models, and scientific algorithms documentation with comprehensive facts and citations.</p></body></html>"
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

    with patch.object(AdaptiveAcquisitionEngine, "acquire_page", side_effect=mock_acquire) as mock_acq, \
         patch("scraper.discovery.providers.registry.ProviderRegistry.search_parallel", new_callable=AsyncMock) as mock_search, \
         patch("scraper.pipeline.search_pipeline.fetch_wikimedia_topic_images", new_callable=AsyncMock) as mock_wm, \
         patch("scraper.pipeline.search_pipeline.fetch_wikipedia_article_images", new_callable=AsyncMock) as mock_wp, \
         patch("scraper.pipeline.search_pipeline.download_media_file", new_callable=AsyncMock) as mock_dm:
        mock_search.return_value = []
        mock_wm.return_value = []
        mock_wp.return_value = []
        mock_dm.return_value = None
        yield mock_acq


@pytest.mark.asyncio
async def test_mcp_tool_inspection():
    res_raw = await deepsearch_inspect("https://example.com/test")
    res = json.loads(res_raw)

    assert res["url"] == "https://example.com/test"
    assert "http_status" in res
    assert "recommended_strategy" in res
    assert "static_score" in res


@pytest.mark.asyncio
async def test_mcp_tool_extraction():
    res_raw = await deepsearch_extract("https://example.com/test")
    res = json.loads(res_raw)

    assert res["url"] == "https://example.com/test"
    assert "clean_markdown" in res
    assert "fit_markdown" in res


@pytest.mark.asyncio
async def test_mcp_tool_search():
    res_raw = await deepsearch_search("quantum mechanics", limit=5)
    res = json.loads(res_raw)

    assert isinstance(res, dict)
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
        auto_discover=False
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
        auto_discover=False
    )
    res = json.loads(res_raw)
    assert res["status"] == "success"


@pytest.mark.asyncio
async def test_mcp_tool_discover():
    with patch("scraper.mcp.server.discover_diverse_seeds", new_callable=AsyncMock) as mock_disc:
        mock_disc.return_value = ["https://arxiv.org/abs/2101.0001"]
        res_raw = await deepsearch_discover(
            query="quantum computing",
            category="science"
        )
        res = json.loads(res_raw)

        assert res["status"] == "success"
        assert res["query"] == "quantum computing"
        assert res["total_seeds"] == 1
        assert res["seeds"] == ["https://arxiv.org/abs/2101.0001"]


def test_mcp_server_metadata():
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]

    assert "deepsearch_research" in tool_names
    assert "deepsearch_inspect" in tool_names
    assert "deepsearch_extract" in tool_names
    assert "deepsearch_search" in tool_names
    assert "deepsearch_discover" in tool_names
