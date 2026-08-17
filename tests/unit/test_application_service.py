"""Unit tests for ResearchApplicationService (DS-A02, DS-A07)."""

import pytest
from scraper.application.models import ResearchRequest, RunLifecycleState
from scraper.application.research_service import DefaultResearchApplicationService
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
