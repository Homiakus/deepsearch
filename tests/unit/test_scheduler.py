"""Unit tests for RequestFrontier and Scheduler (§14, §15)."""

import pytest
from scraper.control.scheduler import RequestFrontier, CrawlRequest, RequestState


@pytest.mark.asyncio
async def test_frontier_add_and_lease():
    frontier = RequestFrontier(max_capacity=100)
    req1 = CrawlRequest(
        url="http://example.com/a",
        canonical_url="http://example.com/a",
        domain="example.com",
        priority=10.0,
    )
    req2 = CrawlRequest(
        url="http://example.com/b",
        canonical_url="http://example.com/b",
        domain="example.com",
        priority=90.0,  # Higher priority
    )

    added1 = await frontier.add_request(req1)
    added2 = await frontier.add_request(req2)
    assert added1 is True
    assert added2 is True

    # Duplicate canonical URL rejected
    dup_req = CrawlRequest(
        url="http://example.com/a?utm_source=google",
        canonical_url="http://example.com/a",
        domain="example.com",
    )
    assert await frontier.add_request(dup_req) is False

    # Highest priority req2 leased first
    leased = await frontier.lease_request(lease_duration_sec=10.0)
    assert leased is not None
    assert leased.id == req2.id
    assert leased.state == RequestState.LEASED
