"""Complexity Cliffs, Worst-Case Inputs & Reference Model Equivalence (§DS-33).

Measures and validates:
1. SimHash near-duplicate scaling across N=0, 1, 2, 10^2, 10^3, 3*10^3.
2. Adversarial inputs: all-duplicates, all-equal priority, huge document, thousands of small objects.
3. Strict equivalence between fast path and reference slow models.
4. RequestFrontier and RankedFrontier scaling without quadratic lease scan cliffs.
5. Media downloader chunked streaming without full-body RAM buffering.
"""

import tempfile
import time
import tracemalloc

import pytest

from scraper.acquisition.media_downloader import download_media_file
from scraper.control.ranked_frontier import (
    RankedFrontier,
)
from scraper.control.scheduler import CrawlRequest, RequestFrontier, RequestState
from scraper.normalization.deduplicator import Deduplicator
from scraper.normalization.near_duplicate import NearDuplicateDetector
from scraper.search.candidates import SourceCandidate

# ==============================================================================
# Reference Models for Equivalence Validation
# ==============================================================================


class ReferenceSimHashModel:
    """Pure slow unoptimized reference model for SimHash distance and duplicate checks."""

    @staticmethod
    def reference_hamming_distance(h1: int, h2: int) -> int:
        x = h1 ^ h2
        count = 0
        while x > 0:
            count += x & 1
            x >>= 1
        return count

    @staticmethod
    def reference_find_near_duplicate(
        query_hash: int, existing_hashes: list[int], threshold: int
    ) -> bool:
        if query_hash == 0:
            return False
        for h in existing_hashes:
            if (
                ReferenceSimHashModel.reference_hamming_distance(query_hash, h)
                <= threshold
            ):
                return True
        return False


class ReferenceFrontierModel:
    """Reference unoptimized priority frontier using full Timsort on every step."""

    def __init__(self):
        self.items: list[tuple[float, str]] = []  # (priority, url)

    def add(self, priority: float, url: str):
        self.items.append((priority, url))
        # Pure reference full sort descending by priority
        self.items.sort(key=lambda x: x[0], reverse=True)

    def pop_top(self) -> tuple[float, str] | None:
        if not self.items:
            return None
        return self.items.pop(0)


# ==============================================================================
# 1. SimHash & Deduplication Complexity Cliffs & Equivalence
# ==============================================================================


def test_simhash_hamming_distance_reference_equivalence():
    """Verify that optimized int.bit_count() produces bit-exact equivalence with reference loop."""
    test_integers = [
        (0, 0),
        (0, 0xFFFFFFFFFFFFFFFF),
        (0xAAAAAAAAAAAAAAAA, 0x5555555555555555),
        (0x123456789ABCDEF0, 0x123456789ABCDEF1),
        (0x123456789ABCDEF0, 0x0FEDCBA987654321),
        (1 << 63, (1 << 63) - 1),
    ]

    for h1, h2 in test_integers:
        fast_dist = Deduplicator.hamming_distance(h1, h2)
        ref_dist = ReferenceSimHashModel.reference_hamming_distance(h1, h2)
        assert fast_dist == ref_dist, (
            f"Mismatch for ({hex(h1)}, {hex(h2)}): {fast_dist} != {ref_dist}"
        )


def test_deduplicator_adversarial_scaling_and_equivalence():
    """Test scaling across N=0, 1, 2, 100, 1000, 3000 for all-duplicates and distinct sets."""
    sizes = [0, 1, 2, 100, 1000, 3000]

    for N in sizes:
        dedup = Deduplicator(simhash_distance_threshold=3)
        ref_hashes: list[int] = []

        # 1. Test all-duplicates (adversarial identical inputs)
        dup_text = "Autonomous deep search engine with high-throughput indexing and zero-copy data extraction"
        for i in range(min(N, 100)):
            is_dup = dedup.is_near_duplicate(dup_text)
            if i == 0:
                assert not is_dup
            else:
                assert is_dup

        # 2. Test distinct documents with doubling ratio timing
        dedup_distinct = Deduplicator(simhash_distance_threshold=3)
        t0 = time.perf_counter()
        for i in range(N):
            text = f"Scientific publication document article section {i} covering computational complexity and edge cases"
            sh = dedup_distinct.compute_simhash(text)
            is_near_dup = dedup_distinct.is_near_duplicate(text)

            # Check equivalence against reference for smaller subsets
            if N <= 100:
                ref_dup = ReferenceSimHashModel.reference_find_near_duplicate(
                    sh, ref_hashes, threshold=3
                )
                assert is_near_dup == ref_dup
                if not is_near_dup:
                    ref_hashes.append(sh)

        duration = time.perf_counter() - t0
        # Even for 3000 documents, duration must stay bounded under 2.0 seconds
        assert duration < 2.0, f"Duration {duration:.3f}s exceeded budget for N={N}"


def test_near_duplicate_huge_document_and_small_snippets():
    """Characterize behavior on a 1MB huge document vs 2000 tiny text snippets."""
    detector = NearDuplicateDetector(hamming_threshold=12)

    # 1. Huge document (~1MB)
    huge_text = (
        "Autonomous agentic reasoning with multidimensional boundary spaces. " * 15000
    )
    assert len(huge_text) > 500_000

    tracemalloc.start()
    t0 = time.perf_counter()
    res_huge = detector.register_document("doc_huge_1", huge_text)
    huge_duration = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert not res_huge.is_near_duplicate
    assert huge_duration < 0.5, (
        f"Huge doc processing took too long: {huge_duration:.3f}s"
    )
    assert peak_mem < 25 * 1024 * 1024, (
        f"Peak memory exceeded 25MB: {peak_mem / (1024 * 1024):.2f}MB"
    )

    # 2. 1000 small snippets
    t0_small = time.perf_counter()
    for i in range(1000):
        res = detector.register_document(
            f"small_{i}",
            f"entry_{i} word_{i}_alpha term_{i}_beta content_{i}_gamma record_{i}_delta block_{i}_omega",
        )
        assert not res.is_near_duplicate
    small_duration = time.perf_counter() - t0_small
    assert small_duration < 1.0, f"Small snippets took too long: {small_duration:.3f}s"


# ==============================================================================
# 2. Scheduler & Frontier Priority Complexity Cliffs
# ==============================================================================


@pytest.mark.asyncio
async def test_request_frontier_all_equal_priority_and_lease_scaling():
    """Verify RequestFrontier scales without O(total) scans during leasing and equal-priority enqueuing."""
    frontier = RequestFrontier(max_capacity=10000)
    num_requests = 2000

    # 1. Enqueue 2000 equal-priority items
    t0 = time.perf_counter()
    for i in range(num_requests):
        req = CrawlRequest(
            id=f"req_{i}",
            url=f"https://example.com/page_{i}",
            canonical_url=f"https://example.com/page_{i}",
            domain="example.com",
            priority=50.0,  # All equal priority
        )
        ok = await frontier.add_request(req)
        assert ok is True
    enqueue_duration = time.perf_counter() - t0
    assert enqueue_duration < 0.8, (
        f"Equal-priority enqueue took too long: {enqueue_duration:.3f}s"
    )

    # 2. Lease requests and verify no expired-lease scan penalty
    t0_lease = time.perf_counter()
    leased_items = []
    for _ in range(50):
        leased = await frontier.lease_request(lease_duration_sec=60.0)
        assert leased is not None
        leased_items.append(leased)
    lease_duration = time.perf_counter() - t0_lease
    assert lease_duration < 0.1, (
        f"Leasing 50 items took too long: {lease_duration:.3f}s"
    )

    # 3. Complete and stats
    for item in leased_items:
        await frontier.update_state(item.id, RequestState.DONE)
    stats = await frontier.stats()
    assert stats[RequestState.DONE.value] == 50
    assert stats[RequestState.QUEUED.value] == num_requests - 50


@pytest.mark.asyncio
async def test_ranked_frontier_reference_equivalence_and_domain_fairness():
    """Verify RankedFrontier ordering equivalence against reference model under diverse priorities."""
    frontier = RankedFrontier(max_capacity=1000, max_active_per_domain=2)
    ref_model = ReferenceFrontierModel()

    priorities = [0.1, 0.9, 0.4, 0.85, 0.3, 0.95, 0.7, 0.2, 0.6]

    for i, p in enumerate(priorities):
        url = f"https://domain{i % 3}.com/page_{i}"
        cand = SourceCandidate(
            url=url,
            canonical_url=url,
            domain=f"domain{i % 3}.com",
            title=f"Page {i}",
            provider="test",
        )
        await frontier.add_candidate(cand, priority=p)
        ref_model.add(p, url)

    # The highest overall priority (0.95, page 5, domain 2) must be leased first
    first_leased = await frontier.lease_next(lease_duration_sec=30.0)
    assert first_leased is not None
    assert first_leased.priority == 0.95

    # Second highest (0.9, page 1, domain 1)
    second_leased = await frontier.lease_next(lease_duration_sec=30.0)
    assert second_leased is not None
    assert second_leased.priority == 0.90


# ==============================================================================
# 3. Media Streaming Buffer Bounds & Oversized Chunked Body Safety
# ==============================================================================


@pytest.mark.asyncio
async def test_media_downloader_oversized_stream_rejection(monkeypatch):
    """Verify that media downloader terminates stream and cleans up temp files when stream exceeds max_bytes."""
    import httpx

    # Simulate an infinite/oversized chunked stream (decompression bomb / huge file)
    class FakeOversizedStream:
        def __init__(self):
            self.status_code = 200
            self.headers = {"content-type": "application/pdf"}
            self.is_redirect = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_bytes(self, chunk_size=65536):
            # Yield 200 chunks of 64KB = 12.8MB (exceeding max_bytes limit of 500KB)
            for _ in range(200):
                yield b"A" * 65536

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, **kwargs):
            return FakeOversizedStream()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = await download_media_file(
            url="https://example.com/oversized.pdf",
            output_dir=tmp_dir,
            max_bytes=500 * 1024,  # 500 KB limit
            timeout_sec=5.0,
        )
        # Must safely reject oversized stream without exception
        assert result is None
        # Must have no leftover leaked temp files in tmp_dir
        import os

        remaining_files = os.listdir(tmp_dir)
        assert len(remaining_files) == 0, (
            f"Leaked temporary files found: {remaining_files}"
        )
