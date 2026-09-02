"""Unit tests for RequestFrontier and Scheduler (§14, §15)."""

import pytest

from scraper.control.scheduler import CrawlRequest, RequestFrontier, RequestState


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


@pytest.mark.asyncio
async def test_mandatory_regression_lease_retry_retry_lease_lease():
    """Mandatory regression sequence: lease, retry, retry, lease, lease -> 2nd returns 1 item, 3rd returns None."""
    sim_time = 1000.0
    frontier = RequestFrontier(max_capacity=10, now_wall=lambda: sim_time)
    req = CrawlRequest(
        url="http://example.com/regression-item",
        canonical_url="http://example.com/regression-item",
        domain="example.com",
        priority=50.0,
        max_attempts=3,
    )
    assert await frontier.add_request(req) is True

    # 1. lease
    l1 = await frontier.lease_request()
    assert l1 is not None
    assert l1.id == req.id
    assert l1.attempt == 1

    # 2. retry
    await frontier.retry_request(req.id)
    assert req.attempt == 2
    assert req.state == RequestState.QUEUED

    # 3. retry (already in queue -> ignored)
    await frontier.retry_request(req.id)
    assert req.attempt == 2
    assert len(frontier._queue) == 1

    # 4. lease -> returns the retried request
    l2 = await frontier.lease_request()
    assert l2 is not None
    assert l2.id == req.id
    assert l2.attempt == 2

    # 5. lease -> returns None because queue is empty
    l3 = await frontier.lease_request()
    assert l3 is None


@pytest.mark.asyncio
async def test_terminal_requests_cannot_be_leased_or_revived():
    """Terminal requests (DONE, DEAD, SKIPPED) must never be leased or retried."""
    frontier = RequestFrontier(max_capacity=10)
    req1 = CrawlRequest(
        url="http://example.com/done",
        canonical_url="http://example.com/done",
        domain="example.com",
    )
    req2 = CrawlRequest(
        url="http://example.com/dead",
        canonical_url="http://example.com/dead",
        domain="example.com",
    )
    req3 = CrawlRequest(
        url="http://example.com/skipped",
        canonical_url="http://example.com/skipped",
        domain="example.com",
    )

    await frontier.add_request(req1)
    await frontier.add_request(req2)
    await frontier.add_request(req3)

    # Transition to terminal states
    await frontier.update_state(req1.id, RequestState.DONE)
    await frontier.update_state(req2.id, RequestState.DEAD)
    await frontier.update_state(req3.id, RequestState.SKIPPED)

    # Attempt to retry terminal requests
    await frontier.retry_request(req1.id)
    await frontier.retry_request(req2.id)
    await frontier.retry_request(req3.id)

    # None should be queued or leased
    assert len(frontier._queue) == 0
    leased = await frontier.lease_request()
    assert leased is None


@pytest.mark.asyncio
async def test_frontier_clock_jumps_and_lease_expiry():
    """FRAG-TIME: Validate lease expiry with simulated time and clock jumps (t-ε, t, t+ε, backward)."""
    current_time = 1000.0

    def get_time() -> float:
        return current_time

    frontier = RequestFrontier(max_capacity=10, now_wall=get_time)
    req_a = CrawlRequest(
        url="http://example.com/a",
        canonical_url="http://example.com/a",
        domain="example.com",
        priority=10.0,
    )
    req_b = CrawlRequest(
        url="http://example.com/b",
        canonical_url="http://example.com/b",
        domain="example.com",
        priority=90.0,
    )

    await frontier.add_request(req_a)
    await frontier.add_request(req_b)

    # Lease highest priority (B) with 10s duration (expires at 1010.0)
    l1 = await frontier.lease_request(lease_duration_sec=10.0)
    assert l1 is not None
    assert l1.id == req_b.id
    assert l1.lease_expires_at == 1010.0

    # At t - ε (1009.9): req_b is still leased, next lease yields req_a
    current_time = 1009.9
    l2 = await frontier.lease_request(lease_duration_sec=5.0)
    assert l2 is not None
    assert l2.id == req_a.id

    # At t = 1009.9: no more items
    l3 = await frontier.lease_request()
    assert l3 is None

    # At t + ε (1010.1): req_b has expired and should be automatically re-queued and leased
    current_time = 1010.1
    l4 = await frontier.lease_request()
    assert l4 is not None
    assert l4.id == req_b.id

    # Backward clock jump (e.g. NTP step backward to 950.0): does not crash
    current_time = 950.0
    l5 = await frontier.lease_request()
    assert l5 is None


@pytest.mark.asyncio
async def test_frontier_capacity_and_stats_partition():
    """Verify capacity bounds and that stats partition accounts for all tracked requests."""
    frontier = RequestFrontier(max_capacity=2)
    req1 = CrawlRequest(
        url="http://example.com/1",
        canonical_url="http://example.com/1",
        domain="example.com",
    )
    req2 = CrawlRequest(
        url="http://example.com/2",
        canonical_url="http://example.com/2",
        domain="example.com",
    )
    req3 = CrawlRequest(
        url="http://example.com/3",
        canonical_url="http://example.com/3",
        domain="example.com",
    )

    assert await frontier.add_request(req1) is True
    assert await frontier.add_request(req2) is True
    # Capacity exceeded
    assert await frontier.add_request(req3) is False

    stats = await frontier.stats()
    assert stats.get(RequestState.QUEUED.value, 0) == 2
    assert sum(stats.values()) == 2

    # Lease one request
    leased = await frontier.lease_request()
    assert leased is not None

    stats = await frontier.stats()
    assert stats.get(RequestState.LEASED.value, 0) == 1
    assert stats.get(RequestState.QUEUED.value, 0) == 1
    assert sum(stats.values()) == 2

    # Now capacity in queue allows adding req3
    assert await frontier.add_request(req3) is True
    stats = await frontier.stats()
    assert sum(stats.values()) == 3


@pytest.mark.asyncio
async def test_stateful_frontier_model_invariants():
    """Stateful model simulation verifying queue uniqueness, monotonic attempts, and state consistency."""
    current_time = 5000.0

    def clock() -> float:
        return current_time

    frontier = RequestFrontier(max_capacity=50, now_wall=clock)
    tracked_attempts: dict[str, int] = {}

    for i in range(15):
        req = CrawlRequest(
            url=f"http://example.com/page-{i}",
            canonical_url=f"http://example.com/page-{i}",
            domain="example.com",
            priority=float(i * 5),
            max_attempts=3,
        )
        added = await frontier.add_request(req)
        assert added is True
        tracked_attempts[req.id] = 1

    leased_items: list[CrawlRequest] = []
    # Lease 5 items
    for _ in range(5):
        item = await frontier.lease_request(lease_duration_sec=30.0)
        assert item is not None
        leased_items.append(item)

    # Invariant checks after leasing
    queue_ids = [r.id for r in frontier._queue]
    assert len(queue_ids) == len(set(queue_ids)), "Queue IDs must be strictly unique"
    for item in leased_items:
        assert item.id not in queue_ids, "Leased items must not be in queue"
        assert item.state == RequestState.LEASED

    # Retry 2 items, complete 2 items, fail 1 item
    await frontier.retry_request(leased_items[0].id)
    tracked_attempts[leased_items[0].id] += 1
    assert leased_items[0].attempt == tracked_attempts[leased_items[0].id]

    await frontier.retry_request(leased_items[1].id)
    tracked_attempts[leased_items[1].id] += 1

    await frontier.update_state(leased_items[2].id, RequestState.DONE)
    await frontier.update_state(leased_items[3].id, RequestState.DONE)
    await frontier.update_state(leased_items[4].id, RequestState.DEAD)

    # Advance time to expire remaining leases (if any)
    current_time += 100.0
    # Lease next available
    next_leased = await frontier.lease_request()
    assert next_leased is not None
    assert next_leased.state == RequestState.LEASED

    # Verify partition sum consistency
    stats = await frontier.stats()
    assert sum(stats.values()) == len(frontier._requests_by_id)
    assert stats.get(RequestState.DONE.value, 0) == 2
    assert stats.get(RequestState.DEAD.value, 0) == 1
