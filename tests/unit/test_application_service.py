"""Unit tests for DeepSearchService and ResearchApplicationService (DS-A02, DS-A07, §DS-04)."""

from unittest.mock import AsyncMock, patch

import pytest

from scraper.acquisition.engine import CapturedArtifact, PageIntelligence
from scraper.application.models import ResearchRequest, RunLifecycleState
from scraper.application.research_service import DefaultResearchApplicationService
from scraper.application.service import (
    DeepSearchService,
    ExtractedContentResult,
    PageInspectionResult,
    get_deepsearch_service,
)
from scraper.config import ExecutionMode


@pytest.mark.asyncio
async def test_research_service_lifecycle():
    service = DefaultResearchApplicationService()
    req = ResearchRequest(
        query="Unit test research",
        domain="example.com",
        preferred_sources=["https://example.com/test"],
        depth=1,
        max_pages=2,
        mode=ExecutionMode.FAST,
        enable_media_archiving=False,
        auto_discover=False,
    )

    handle = await service.start(req)
    assert handle.run_id.startswith("ds_run_")
    assert handle.status in (RunLifecycleState.PENDING, RunLifecycleState.RUNNING)

    status = await service.status(handle.run_id)
    assert status.run_id == handle.run_id
    assert status.status in (RunLifecycleState.RUNNING, RunLifecycleState.COMPLETED)


@pytest.mark.asyncio
async def test_research_service_idempotency():
    service = DefaultResearchApplicationService()
    req = ResearchRequest(
        query="Idempotent test query",
        depth=1,
        max_pages=1,
        mode=ExecutionMode.FAST,
        idempotency_key="idemp_key_12345",
        enable_media_archiving=False,
        auto_discover=False,
    )

    handle1 = await service.start(req)
    handle2 = await service.start(req)

    assert handle1.run_id == handle2.run_id
    assert handle2.idempotency_key == "idemp_key_12345"


@pytest.mark.asyncio
async def test_research_service_cancellation():
    service = DefaultResearchApplicationService()
    req = ResearchRequest(
        query="Cancel test query",
        depth=2,
        max_pages=10,
        mode=ExecutionMode.BALANCED,
        auto_discover=False,
    )

    handle = await service.start(req)
    await service.cancel(handle.run_id)

    status = await service.status(handle.run_id)
    assert status.status == RunLifecycleState.CANCELLED


@pytest.mark.asyncio
async def test_deepsearch_service_inspect_and_extract():
    fake_artifact = CapturedArtifact(
        url="https://example.com/doc",
        canonical_url="https://example.com/doc",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"<html><body><h1>Title</h1><p>Sample text content</p></body></html>",
        text_content="<html><body><h1>Title</h1><p>Sample text content</p></body></html>",
        page_intelligence=PageIntelligence(
            static_score=0.9,
            js_dependency_score=0.1,
            detected_apis=[],
            tables_count=0,
            has_canvas=False,
            visual_score=0.2,
        ),
    )

    mock_acq = AsyncMock()
    mock_acq.acquire_page.return_value = fake_artifact

    service = DeepSearchService(acquisition_engine=mock_acq)

    # Test inspect
    inspect_res = await service.inspect("https://example.com/doc")
    assert isinstance(inspect_res, PageInspectionResult)
    assert inspect_res.http_status == 200
    assert inspect_res.recommended_strategy == "HTTP"
    assert inspect_res.canonical_url == "https://example.com/doc"

    # Test extract
    extract_res = await service.extract("https://example.com/doc")
    assert isinstance(extract_res, ExtractedContentResult)
    assert "Title" in extract_res.clean_markdown
    assert "Sample text content" in extract_res.clean_markdown

    # Test close lifecycle
    await service.close()


def test_get_deepsearch_service_composition_root():
    s1 = get_deepsearch_service()
    s2 = get_deepsearch_service()
    assert s1 is s2
    assert isinstance(s1, DeepSearchService)


@pytest.mark.asyncio
async def test_interface_parity_inspect_and_extract():
    """Verify FastAPI, MCP, and Service produce identical domain results for inspect (§DS-04)."""
    import json

    from fastapi.testclient import TestClient

    from scraper.api.app import app
    from scraper.mcp.server import deepsearch_extract, deepsearch_inspect

    fake_artifact = CapturedArtifact(
        url="https://example.com/contract",
        canonical_url="https://example.com/contract",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"<html><body><h1>Contract Parity</h1><p>Deterministic content</p></body></html>",
        text_content="<html><body><h1>Contract Parity</h1><p>Deterministic content</p></body></html>",
        page_intelligence=PageIntelligence(
            static_score=0.95,
            js_dependency_score=0.05,
            detected_apis=[],
            tables_count=0,
            has_canvas=False,
            visual_score=0.1,
        ),
    )

    mock_acq = AsyncMock()
    mock_acq.acquire_page.return_value = fake_artifact
    mock_acq.browser_pool = AsyncMock()
    mock_acq.http_fetcher = AsyncMock()

    service = DeepSearchService(acquisition_engine=mock_acq)

    # 1. Direct Service Call
    direct_inspect = await service.inspect("https://example.com/contract")
    direct_extract = await service.extract("https://example.com/contract")

    # 2. FastAPI TestClient with injected dependency override
    app.dependency_overrides[get_deepsearch_service] = lambda: service
    try:
        client = TestClient(app)
        api_res = client.post(
            "/api/v1/inspect",
            headers={"X-API-Key": "dev-secret"},
            json={"url": "https://example.com/contract"},
        )
        assert api_res.status_code == 200
        api_data = api_res.json()
    finally:
        app.dependency_overrides.clear()

    # 3. MCP Tool Function with mocked service provider
    with patch("scraper.mcp.server.get_deepsearch_service", return_value=service):
        mcp_res_json = await deepsearch_inspect("https://example.com/contract")
        mcp_data = json.loads(mcp_res_json)

        mcp_extract_json = await deepsearch_extract("https://example.com/contract")
        mcp_extract_data = json.loads(mcp_extract_json)

    # Assert exact domain result parity across all three interfaces
    assert (
        direct_inspect.url
        == api_data["url"]
        == mcp_data["url"]
        == "https://example.com/contract"
    )
    assert (
        direct_inspect.http_status
        == api_data["http_status"]
        == mcp_data["http_status"]
        == 200
    )
    assert (
        direct_inspect.recommended_strategy
        == api_data["recommended_strategy"]
        == mcp_data["recommended_strategy"]
        == "HTTP"
    )
    assert (
        direct_inspect.static_score
        == api_data["static_score"]
        == mcp_data["static_score"]
    )

    assert direct_extract.clean_markdown == mcp_extract_data["clean_markdown"]
    assert "Contract Parity" in direct_extract.clean_markdown

    # Assert clean lifecycle close
    await service.close()
    assert mock_acq.browser_pool.close.called
    assert mock_acq.http_fetcher.close.called
