"""Unit tests for Distributed Request Queue Adapter."""

import pytest
from scraper.control.distributed_queue import (
    InMemoryDistributedQueue,
    get_distributed_queue,
)
from scraper.control.scheduler import CrawlRequest, RequestState


@pytest.mark.asyncio
async def test_in_memory_distributed_queue_lifecycle():
    queue = InMemoryDistributedQueue(max_capacity=10)

    req1 = CrawlRequest(
        url="https://example.com/page1",
        canonical_url="https://example.com/page1",
        domain="example.com",
    )
    req2 = CrawlRequest(
        url="https://example.com/page2",
        canonical_url="https://example.com/page2",
        domain="example.com",
    )

    # 1. Push
    assert await queue.push(req1) is True
    assert await queue.push(req2) is True

    stats = await queue.get_stats()
    assert stats["queued_count"] == 2

    # 2. Pop batch
    leased = await queue.pop_batch(consumer_name="worker-1", count=1)
    assert len(leased) == 1
    msg_id1, leased_req1 = leased[0]
    assert leased_req1.url == "https://example.com/page1"
    assert leased_req1.state == RequestState.LEASED

    stats_after_pop = await queue.get_stats()
    assert stats_after_pop["queued_count"] == 1
    assert stats_after_pop["pending_count"] == 1

    # 3. Ack
    assert await queue.ack(msg_id1) is True
    stats_after_ack = await queue.get_stats()
    assert stats_after_ack["pending_count"] == 0
    assert stats_after_ack["ack_count"] == 1

    # 4. Pop next and Nack (requeue)
    leased2 = await queue.pop_batch(consumer_name="worker-1", count=1)
    assert len(leased2) == 1
    msg_id2, leased_req2 = leased2[0]

    assert await queue.nack(msg_id2, requeue=True) is True
    stats_after_nack = await queue.get_stats()
    assert stats_after_nack["queued_count"] == 1
    assert stats_after_nack["nack_count"] == 1

    await queue.close()


def test_get_distributed_queue_factory():
    q = get_distributed_queue(backend="memory")
    assert isinstance(q, InMemoryDistributedQueue)
