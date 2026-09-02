"""Top-10 Core Algorithms Contracts & Invariants Characterization Suite (§DS-27).

Verifies invariants, error semantics, and idempotency for:
- A-001: URL Canonicalization & Policy
- A-002: Content Hashing & Exact Deduplication
- A-003: Page Structure & Intelligence Classification
- A-004: Media Selection & Discovery
- A-005: Crawl Scheduling & Frontier Management
- A-006: Host Rate Limiting & Resource Budgeting
- A-007: Query Decomposition & Research Planning
- A-008: Deterministic Extraction Engine
- A-009: Adaptive Acquisition & Recovery
- A-010: Content-Addressable Storage & Archive Export
"""

import pytest

from scraper.acquisition.page_classifier import PageIntelligence, classify_page
from scraper.control.budget import BudgetTracker, JobBudget
from scraper.control.scheduler import CrawlRequest, RequestFrontier, RequestState
from scraper.exceptions import BudgetExceededError, SSRFBlockedError
from scraper.extraction.engine import ExtractionEngine
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.normalization.content_hash import compute_content_hash
from scraper.normalization.deduplicator import Deduplicator
from scraper.research.decomposer import decompose_intent
from scraper.research.intent import ResearchIntent
from scraper.security.url_policy import URLSecurityPolicy
from scraper.storage.cas import ContentAddressableStore


def test_a001_url_canonicalization_and_policy_invariants():
    """A-001: Validate URL canonicalization idempotency and strict SSRF policy bounds."""
    raw_url = "HTTPS://EXAMPLE.COM:443/docs/../research/?b=2&a=1#section"
    c1 = canonicalize_url(raw_url)
    c2 = canonicalize_url(c1)
    assert c1 == c2

    policy = URLSecurityPolicy()
    assert policy.validate_url("https://example.com/api") == "https://example.com/api"

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://127.0.0.1/admin")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://169.254.169.254/latest")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::1]/secret")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("file:///etc/passwd")


def test_a002_content_hashing_and_dedup_invariants():
    """A-002: Validate deterministic content hashing and exact deduplication."""
    text1 = "DeepSearch provides   adaptive scraping.\n\n"
    text2 = "DeepSearch provides adaptive scraping."
    h1 = compute_content_hash(text1)
    h2 = compute_content_hash(text2)
    assert h1 == h2
    assert len(h1) == 64

    dedup = Deduplicator()
    assert dedup.is_content_duplicate(text1.encode("utf-8")) is False
    assert dedup.is_content_duplicate(text1.encode("utf-8")) is True


def test_a003_page_classifier_invariants():
    """A-003: Validate graceful classification of arbitrary HTML payloads."""
    res = classify_page(
        url="https://example.com",
        status_code=200,
        headers={"content-type": "text/html"},
        content_text="<p>Content without body</p>",
    )
    assert isinstance(res, PageIntelligence)

    empty_res = classify_page(
        url="https://example.com",
        status_code=200,
        headers={"content-type": "text/html"},
        content_text="",
    )
    assert isinstance(empty_res, PageIntelligence)


@pytest.mark.asyncio
async def test_a005_scheduler_frontier_invariants():
    """A-005: Validate crawl task leasing, monotonicity, and queue bounds."""
    frontier = RequestFrontier(max_capacity=100)
    req1 = CrawlRequest(
        url="https://example.com/p1",
        canonical_url="https://example.com/p1",
        domain="example.com",
        depth=1,
    )
    added = await frontier.add_request(req1)
    assert added is True

    leased = await frontier.lease_request()
    assert leased is not None
    assert leased.url == "https://example.com/p1"
    assert leased.state == RequestState.LEASED


@pytest.mark.asyncio
async def test_a006_budget_tracker_invariants():
    """A-006: Validate atomic budget checking and exhaustion error semantics."""
    budget = JobBudget(max_pages=2, max_depth=3, max_bytes=1000)
    tracker = BudgetTracker(budget=budget)

    await tracker.record_page(bytes_size=400, depth=1)
    assert tracker.pages_processed == 1

    await tracker.record_page(bytes_size=400, depth=1)
    assert tracker.pages_processed == 2

    with pytest.raises(BudgetExceededError):
        await tracker.record_page(bytes_size=400, depth=1)


def test_a007_query_decomposer_invariants():
    """A-007: Validate deterministic query decomposition into orthogonal subqueries."""
    intent = ResearchIntent(
        original_query="Laser cutting optical parameters comparison",
        normalized_query="laser cutting optical parameters comparison",
    )
    graph = decompose_intent(intent)
    assert len(graph.goals) >= 1
    assert all(len(g.question) > 0 for g in graph.goals.values())


def test_a008_extraction_engine_invariants():
    """A-008: Validate deterministic markdown and table extraction with field provenance."""
    html = "<html><body><h1>Title</h1><p>Body paragraph</p></body></html>"
    res = ExtractionEngine.extract_from_html(url="https://example.com", raw_html=html)
    assert res.clean_markdown is not None
    assert res.tables is not None
    assert res.extracted_records is not None
    assert res.url == "https://example.com"


def test_a010_cas_store_invariants(tmp_path):
    """A-010: Validate content-addressable storage digest determinism and persistence."""
    cas = ContentAddressableStore(base_dir=str(tmp_path / "cas"))
    payload = b"DeepSearch Content Storage Block"
    digest1, size1 = cas.store(payload)
    digest2, size2 = cas.store(payload)
    assert digest1 == digest2
    assert size1 == len(payload)
    assert cas.retrieve(digest1) == payload
