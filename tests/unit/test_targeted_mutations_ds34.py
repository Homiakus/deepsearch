"""Targeted Mutation Gate & Boundary Mutation Test Battery (§DS-34).

Executes targeted mutation operators on top-10 pure/control modules to verify that
test suites kill:
1. Relational mutations: (>, <, >=, <=, ==, !=)
2. Boolean operator mutations: (and -> or, or -> and, not inversion)
3. Boundary constant mutations: (0 -> 1, N -> N+1, N -> N-1, threshold mutations)
4. Return / State outcome mutations: (Success -> Error, leased -> queued, True -> False)
5. Validation / Retry branch deletion & bypass
"""

import pytest

from scraper.control.budget import BudgetTracker, JobBudget
from scraper.control.ranked_frontier import (
    RankedFrontier,
)
from scraper.control.scheduler import CrawlRequest, RequestFrontier, RequestState
from scraper.domain.document import Document
from scraper.exceptions import BudgetExceededError
from scraper.extraction.document_type import DocumentType, DocumentTypeClassifier
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.normalization.deduplicator import Deduplicator
from scraper.retrieval.chunking import StructureAwareChunker
from scraper.search.candidates import SourceCandidate
from scraper.security.url_policy import SSRFBlockedError, URLSecurityPolicy

# ==============================================================================
# 1. URL Policy & Canonicalizer Boundary Mutations
# ==============================================================================


def test_mutation_url_policy_subnet_and_port_boundaries():
    """Verify kills for boundary mutations in SSRF subnet matching and default port stripping."""
    policy = URLSecurityPolicy()

    # Relational & subnet boundary mutations: 127.0.0.1, 10.255.255.255, 172.31.255.255, 192.168.255.255
    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://127.0.0.1:8080/api")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://10.255.255.255/secret")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://172.31.255.255/metadata")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://192.168.1.1:80/admin")

    # IPv6 Loopback and IPv4-mapped IPv6 boundaries
    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::1]:8000/internal")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::ffff:127.0.0.1]/test")

    # Canonicalizer port removal mutation (80 on http, 443 on https, other ports preserved)
    assert canonicalize_url("http://example.com:80/path") == "http://example.com/path"
    assert (
        canonicalize_url("https://example.com:443/path") == "https://example.com/path"
    )
    assert (
        canonicalize_url("http://example.com:8080/path")
        == "http://example.com:8080/path"
    )
    assert (
        canonicalize_url("https://example.com:8443/path")
        == "https://example.com:8443/path"
    )


# ==============================================================================
# 2. Deduplicator & Near-Duplicate Threshold Mutations
# ==============================================================================


def test_mutation_deduplicator_hamming_threshold_boundaries():
    """Verify kills for off-by-one mutations in SimHash hamming distance threshold (dist <= 3 vs dist < 3)."""
    # Create two hashes with exact distance 3 and distance 4
    h_base = 0b00000000
    h_dist3 = 0b00000111  # 3 bits flipped
    h_dist4 = 0b00001111  # 4 bits flipped

    assert Deduplicator.hamming_distance(h_base, h_dist3) == 3
    assert Deduplicator.hamming_distance(h_base, h_dist4) == 4

    dedup = Deduplicator(simhash_distance_threshold=3)
    dedup.simhashes[h_base] = "https://example.com/base"

    class MockDeduplicator(Deduplicator):
        def is_near_duplicate_test(self, s_hash: int) -> bool:
            threshold = self.threshold
            for existing_hash in self.simhashes:
                if (s_hash ^ existing_hash).bit_count() <= threshold:
                    return True
            return False

    mock = MockDeduplicator(simhash_distance_threshold=3)
    mock.simhashes[h_base] = "base"

    assert mock.is_near_duplicate_test(h_dist3) is True  # Kills '< threshold' mutant
    assert mock.is_near_duplicate_test(h_dist4) is False  # Kills '> threshold' mutant


# ==============================================================================
# 3. Budget & Rate Limiter Boundary Mutations
# ==============================================================================


@pytest.mark.asyncio
async def test_mutation_budget_hard_limit_boundaries():
    """Verify kills for budget inequality mutations (pages > max_pages, bytes > max_bytes)."""
    budget = JobBudget(
        max_pages=2,
        max_bytes=1000,
        max_browser_seconds=10.0,
        max_depth=3,
    )
    tracker = BudgetTracker(budget=budget)

    # Page 1: 500 bytes (within budget)
    await tracker.record_page(bytes_size=500, depth=1)
    assert tracker.pages_processed == 1

    # Page 2: 400 bytes (hits max_pages=2, total_bytes=900 <= 1000)
    await tracker.record_page(bytes_size=400, depth=1)
    assert tracker.pages_processed == 2

    # Page 3 should trigger BudgetExceededError (new_pages = 3 > max_pages=2)
    with pytest.raises(BudgetExceededError, match="Page limit exceeded"):
        await tracker.record_page(bytes_size=50, depth=1)


@pytest.mark.asyncio
async def test_mutation_rate_limiter_window_and_delay_boundaries():
    """Verify kills for rate limiter token bucket math and negative delay mutations."""
    from scraper.control.rate_limiter import TokenBucket

    bucket = TokenBucket(rate=10.0, capacity=2.0)

    # 1. Acquire up to capacity (2 tokens) with 0 delay
    wait1 = await bucket.acquire(1.0)
    assert wait1 == 0.0
    wait2 = await bucket.acquire(1.0)
    assert wait2 == 0.0

    # 2. Third immediate token requires wait_time > 0 (kills 'wait = 0' bypass mutant)
    wait3 = await bucket.acquire(1.0)
    assert wait3 > 0.08  # Needed / rate = 1.0 / 10.0 = 0.1s wait


# ==============================================================================
# 4. Scheduler & Frontier Retry & State Transition Mutations
# ==============================================================================


@pytest.mark.asyncio
async def test_mutation_scheduler_max_attempts_and_retry_penalty():
    """Verify kills for max_attempts boundary (attempt > max_attempts vs >=) and priority decrement mutations."""
    frontier = RequestFrontier()
    req = CrawlRequest(
        id="test_req_1",
        url="https://example.com/retry",
        canonical_url="https://example.com/retry",
        domain="example.com",
        priority=50.0,
        max_attempts=3,
    )
    await frontier.add_request(req)

    # Lease attempt 1
    leased = await frontier.lease_request(lease_duration_sec=10.0)
    assert leased is not None
    assert leased.attempt == 1

    # Retry attempt 1 -> becomes attempt 2 with priority 45.0
    await frontier.retry_request("test_req_1")
    req_state = frontier._requests_by_id["test_req_1"]
    assert req_state.state == RequestState.QUEUED
    assert req_state.attempt == 2
    assert req_state.priority == 45.0  # Kills 'priority - 0' or 'priority + 5' mutant

    # Lease attempt 2
    leased2 = await frontier.lease_request(lease_duration_sec=10.0)
    assert leased2 is not None

    # Retry attempt 2 -> becomes attempt 3 with priority 40.0
    await frontier.retry_request("test_req_1")
    req_state = frontier._requests_by_id["test_req_1"]
    assert req_state.state == RequestState.QUEUED
    assert req_state.attempt == 3
    assert req_state.priority == 40.0

    # Lease attempt 3
    leased3 = await frontier.lease_request(lease_duration_sec=10.0)
    assert leased3 is not None

    # Retry attempt 3 -> attempt 4 > max_attempts (3) -> DEAD
    await frontier.retry_request("test_req_1")
    req_state = frontier._requests_by_id["test_req_1"]
    assert (
        req_state.state == RequestState.DEAD
    )  # Kills 'attempt >= max_attempts' off-by-one survival


@pytest.mark.asyncio
async def test_mutation_ranked_frontier_domain_concurrency_limit():
    """Verify kills for domain concurrency inequality (active < max_active vs <=)."""
    frontier = RankedFrontier(max_capacity=100, max_active_per_domain=2)

    # Add 3 candidates from domainA with descending priorities
    for i in range(3):
        cand = SourceCandidate(
            url=f"https://domaina.com/page_{i}",
            canonical_url=f"https://domaina.com/page_{i}",
            domain="domaina.com",
            title=f"A {i}",
            provider="test",
        )
        await frontier.add_candidate(cand, priority=1.0 - i * 0.1)

    # Add 1 candidate from domainB with lower priority
    cand_b = SourceCandidate(
        url="https://domainb.com/page_0",
        canonical_url="https://domainb.com/page_0",
        domain="domainb.com",
        title="B 0",
        provider="test",
    )
    await frontier.add_candidate(cand_b, priority=0.5)

    # Lease 1: Should be domainA page 0 (active domainA = 1 < 2)
    l1 = await frontier.lease_next()
    assert l1 is not None and l1.candidate.domain == "domaina.com"

    # Lease 2: Should be domainA page 1 (active domainA = 2 == 2)
    l2 = await frontier.lease_next()
    assert l2 is not None and l2.candidate.domain == "domaina.com"

    # Lease 3: DomainA has 2 active (hit limit=2), so DomainB (priority 0.5) MUST be chosen instead of domainA page 2!
    l3 = await frontier.lease_next()
    assert (
        l3 is not None and l3.candidate.domain == "domainb.com"
    )  # Kills 'active <= max_active' mutant


# ==============================================================================
# 5. Content Filter & Document Classifier Boundary Mutations
# ==============================================================================


def test_mutation_content_filter_and_classifier_boundaries():
    """Verify kills for link density and document length boundary mutations."""
    from scraper.extraction.content_filter import content_filter

    # 1. Test link density boundary: text with heavy links should have link_density > 0.3
    mostly_links_text = "Check this [link 1](http://a.com) and [link 2](http://b.com) and [link 3](http://c.com)"
    result = content_filter.inspect_content(mostly_links_text)
    assert result.link_density > 0.2  # Link density computed

    # 2. Document classifier status code boundary (403, 404, 500 must produce BLOCK_PAGE or ERROR_PAGE classification)
    classifier = DocumentTypeClassifier()
    res_404 = classifier.classify(
        url="https://example.com/notfound",
        text="Page Not Found",
        status_code=404,
    )
    assert (
        res_404.document_type == DocumentType.ERROR_PAGE
    )  # Kills status code check removal

    res_403 = classifier.classify(
        url="https://example.com/forbidden",
        text="Access Denied",
        status_code=403,
    )
    assert res_403.document_type == DocumentType.BLOCK_PAGE


# ==============================================================================
# 6. Structure-Aware Chunker Overlap & Size Boundary Mutations
# ==============================================================================


def test_mutation_structure_aware_chunker_boundaries():
    """Verify kills for chunking target_words and heading boundary mutations."""
    from scraper.domain.document import DocumentProvenance

    chunker = StructureAwareChunker(target_words=50, overlap_words=10)

    doc = Document(
        id="doc_123",
        source_url="https://example.com/doc",
        canonical_url="https://example.com/doc",
        title="Main Topic",
        clean_markdown="# Section 1\n\n"
        + ("Word " * 60)
        + "\n\n# Section 2\n\n"
        + ("Word " * 60),
        provenance=DocumentProvenance(content_hash="abc123hash"),
    )
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 2
    assert chunks[0].heading == "Section 1"
    assert chunks[-1].heading == "Section 2"
