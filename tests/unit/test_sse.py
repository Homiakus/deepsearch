"""Unit tests for Server-Sent Events (SSE) Broker."""

import pytest
from scraper.api.sse import SSEEventBroker


@pytest.mark.asyncio
async def test_sse_broker_publish_and_subscribe():
    broker = SSEEventBroker()
    job_id = "test_job_123"

    gen = broker.subscribe(job_id)
    # Get initial connection ping
    ping = await anext(gen)
    assert "event: connected" in ping

    # Publish an event
    await broker.publish(job_id, "stage_change", {"stage": "ACQUIRE", "pages": 5})

    # Read from stream
    ev_str = await anext(gen)
    assert "event: stage_change" in ev_str
    assert '"stage": "ACQUIRE"' in ev_str

    # Publish completion
    await broker.publish(job_id, "completed", {"total_claims": 12})
    ev_comp = await anext(gen)
    assert "event: completed" in ev_comp
    assert '"total_claims": 12' in ev_comp

    await broker.clear_job(job_id)
