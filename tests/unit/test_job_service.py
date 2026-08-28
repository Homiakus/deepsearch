"""Unit tests for JobService and crawl job lifecycle (§DS-11)."""

import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from scraper.application.job_service import (
    JobService,
    JobRequest,
    JobLifecycleState,
)
from scraper.acquisition.engine import CapturedArtifact, PageIntelligence
from scraper.exceptions import BudgetExceededError
from scraper.api.app import create_app
from scraper.config import settings


@pytest.fixture
def fake_artifact():
    return CapturedArtifact(
        url="https://example.com/item",
        canonical_url="https://example.com/item",
        strategy_used="L1_HTTP",
        status_code=200,
        content_type="text/html",
        raw_content=b"<html><body><h1>Test Item</h1></body></html>",
        text_content="<html><body><h1>Test Item</h1></body></html>",
        page_intelligence=PageIntelligence(),
    )


@pytest.mark.asyncio
async def test_job_service_lifecycle_success(fake_artifact):
    mock_acq = AsyncMock()
    mock_acq.acquire_page.return_value = fake_artifact

    service = JobService(acquisition_engine=mock_acq)
    req = JobRequest(url="https://example.com/item", max_pages=5)

    handle = await service.submit_job(req)
    assert handle.job_id.startswith("job_")
    assert handle.status == JobLifecycleState.QUEUED

    # Wait briefly for background execution
    await asyncio.sleep(0.05)

    status = await service.get_status(handle.job_id)
    assert status.status == JobLifecycleState.SUCCEEDED
    assert status.pages_processed == 1

    result = await service.get_result(handle.job_id)
    assert result is not None
    assert result.status == JobLifecycleState.SUCCEEDED
    assert result.artifacts_count == 1

    await service.close()


@pytest.mark.asyncio
async def test_job_service_cancellation():
    mock_acq = AsyncMock()

    async def slow_acquire(*args, **kwargs):
        await asyncio.sleep(1.0)
        return fake_artifact

    mock_acq.acquire_page.side_effect = slow_acquire

    service = JobService(acquisition_engine=mock_acq)
    req = JobRequest(url="https://example.com/slow")

    handle = await service.submit_job(req)
    cancelled = await service.cancel_job(handle.job_id)
    assert cancelled is True

    status = await service.get_status(handle.job_id)
    assert status.status == JobLifecycleState.CANCELLED

    await service.close()


@pytest.mark.asyncio
async def test_job_service_queue_full_raises_error():
    service = JobService(max_queue_capacity=1)
    req = JobRequest(url="https://example.com/1")

    await service.submit_job(req)

    # Second submission exceeds capacity
    with pytest.raises(BudgetExceededError, match="queue capacity"):
        await service.submit_job(JobRequest(url="https://example.com/2"))

    await service.close()


@pytest.mark.asyncio
async def test_job_service_unknown_id_raises_key_error():
    service = JobService()
    with pytest.raises(KeyError, match="not found"):
        await service.get_status("nonexistent_job")

    with pytest.raises(KeyError, match="not found"):
        await service.get_result("nonexistent_job")

    with pytest.raises(KeyError, match="not found"):
        await service.cancel_job("nonexistent_job")

    await service.close()


def test_api_crawl_endpoints_integration():
    """Verify REST API crawl job endpoints return 202, 404, and correct states (§DS-11)."""
    client = TestClient(create_app())
    headers = {"X-API-Key": settings.api_key}

    # 1. Unknown job returns 404
    res_404 = client.get("/api/v1/crawl/unknown_job_id", headers=headers)
    assert res_404.status_code == 404

    # 2. Submit crawl job returns 202 with status=queued
    res_submit = client.post(
        "/api/v1/crawl",
        headers=headers,
        json={"url": "https://example.com/test", "max_pages": 5},
    )
    assert res_submit.status_code == 202
    data = res_submit.json()
    assert "job_id" in data
    assert data["status"] == "queued"

    job_id = data["job_id"]

    # 3. Status can be queried
    res_status = client.get(f"/api/v1/crawl/{job_id}", headers=headers)
    assert res_status.status_code == 200
    assert res_status.json()["job_id"] == job_id
