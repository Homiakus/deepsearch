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


@pytest.mark.asyncio
async def test_retry_is_idempotent():
    """FRAG-004: Multiple retries of a leased request must not place duplicate items into the queue."""
    frontier = RequestFrontier(max_capacity=100)
    req = CrawlRequest(
        url="http://example.com/item",
        canonical_url="http://example.com/item",
        domain="example.com",
    )
    await frontier.add_request(req)
    leased = await frontier.lease_request()
    assert leased is not None

    # Call retry twice
    await frontier.retry_request(req.id)
    await frontier.retry_request(req.id)

    # First lease gets the retried request
    l1 = await frontier.lease_request()
    assert l1 is not None
    assert l1.id == req.id

    # Second lease must return None (not duplicate copy)
    l2 = await frontier.lease_request()
    assert l2 is None
