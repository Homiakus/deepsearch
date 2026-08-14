"""Unit tests for DeepSearch MCP Server."""

import json
import pytest
from scraper.mcp.server import (
    deepsearch_inspect,
    deepsearch_extract,
    deepsearch_search,
    deepsearch_research,
    deepsearch_discover,
    mcp
)


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

    assert isinstance(res, list)
    assert len(res) > 0
    assert "title" in res[0]
    assert "score" in res[0]


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
    res_raw = await deepsearch_discover(
        query="quantum computing",
        category="science"
    )
    res = json.loads(res_raw)

    assert res["status"] == "success"
    assert res["query"] == "quantum computing"
    assert "total_seeds" in res
    assert "seeds" in res
    assert isinstance(res["seeds"], list)


def test_mcp_server_metadata():
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]

    assert "deepsearch_research" in tool_names
    assert "deepsearch_inspect" in tool_names
    assert "deepsearch_extract" in tool_names
    assert "deepsearch_search" in tool_names
    assert "deepsearch_discover" in tool_names

