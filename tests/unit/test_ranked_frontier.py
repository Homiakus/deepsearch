"""Unit tests for Ranked Frontier & Retry Lifecycle (DS-SI23 - DS-SI27)."""

import pytest

from scraper.control.ranked_frontier import CandidateState, RankedFrontier
from scraper.search.candidates import SourceCandidate


@pytest.mark.asyncio
async def test_ranked_frontier_priority_and_lease():
    frontier = RankedFrontier(max_capacity=100)

    c_low = SourceCandidate(
        url="https://site.org/low", canonical_url="https://site.org/low", provider="web"
    )
    c_high = SourceCandidate(
        url="https://site.org/high",
        canonical_url="https://site.org/high",
        provider="pubmed",
    )

    await frontier.add_candidate(c_low, priority=0.2)
    await frontier.add_candidate(c_high, priority=0.9)

    assert frontier.size() == 2

    # Top priority leased first
    item1 = await frontier.lease_next(lease_duration_sec=10.0)
    assert item1 is not None
    assert item1.candidate.url == "https://site.org/high"
    assert item1.state == CandidateState.LEASED

    # Second item leased next
    item2 = await frontier.lease_next(lease_duration_sec=10.0)
    assert item2 is not None
    assert item2.candidate.url == "https://site.org/low"


@pytest.mark.asyncio
async def test_ranked_frontier_retry_semantics():
    frontier = RankedFrontier(max_capacity=100)
    c = SourceCandidate(
        url="https://timeout-domain.com/item",
        canonical_url="https://timeout-domain.com/item",
        provider="web",
    )

    await frontier.add_candidate(c, priority=0.8)
    item = await frontier.lease_next(lease_duration_sec=10.0)

    # Transient error retry
    await frontier.mark_state(
        item.id, CandidateState.RETRY, error="ReadTimeout", is_transient_error=True
    )
    assert frontier.size() == 1

    # Lease again after retry
    item_retried = await frontier.lease_next(lease_duration_sec=10.0)
    assert item_retried is not None
    assert item_retried.attempt == 2
    assert item_retried.state == CandidateState.LEASED
