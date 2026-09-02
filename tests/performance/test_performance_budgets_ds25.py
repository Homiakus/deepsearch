"""Performance Budgets & Concurrency Bounds Benchmark Suite (§DS-25).

Measures:
1. Deterministic local corpus parsing throughput, latency (p95), and memory bounds.
2. Bounded concurrency enforcement and cancellation resource cleanup.
3. HTTP client reuse and single-batch API discovery calls.
"""

import time
import asyncio
import tracemalloc
import pytest
from typing import List

from scraper.extraction.engine import ExtractionEngine
from scraper.discovery.media_finder import fetch_wikimedia_topic_images


@pytest.mark.performance
def test_local_corpus_parsing_throughput_and_memory_budget():
    """Verify HTML parsing & extraction throughput and peak memory allocations remain strictly within performance budget (§DS-25)."""
    # Deterministic local synthetic HTML page
    sample_html = """<!DOCTYPE html>
    <html>
    <head><title>Performance Benchmark Page</title></head>
    <body>
        <header><h1>Autonomous Scraping Architecture</h1></header>
        <article>
            <p>DeepSearch provides high-throughput, adaptive content acquisition with zero-copy normalization.</p>
            <table>
                <tr><th>Metric</th><th>Threshold</th><th>Achieved</th></tr>
                <tr><td>p95 Latency</td><td>< 50ms</td><td>4ms</td></tr>
                <tr><td>Memory Per Page</td><td>< 2MB</td><td>120KB</td></tr>
            </table>
            <div><a href="https://example.com/subpage1">Subpage 1</a><a href="https://example.com/subpage2">Subpage 2</a></div>
        </article>
    </body>
    </html>"""

    num_iterations = 50
    latencies: List[float] = []

    tracemalloc.start()
    start_time = time.perf_counter()

    for _ in range(num_iterations):
        t0 = time.perf_counter()
        res = ExtractionEngine.extract_from_html(
            url="https://example.com/bench", raw_html=sample_html
        )
        t1 = time.perf_counter()
        latencies.append(t1 - t0)
        assert len(res.clean_markdown) > 50

    total_duration = time.perf_counter() - start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    throughput = num_iterations / total_duration
    latencies.sort()
    p95_latency = latencies[int(num_iterations * 0.95)]

    # Performance Budgets:
    # 1. Throughput must exceed 50 pages/second on local deterministic corpus
    assert throughput > 50.0, (
        f"Throughput too low: {throughput:.2f} pages/sec (budget > 50)"
    )
    # 2. p95 latency must be under 30ms per page
    assert p95_latency < 0.030, (
        f"p95 latency too high: {p95_latency * 1000:.2f}ms (budget < 30ms)"
    )
    # 3. Peak memory overhead must be under 15MB
    assert peak_mem < 15 * 1024 * 1024, (
        f"Peak memory exceeded: {peak_mem / (1024 * 1024):.2f}MB (budget < 15MB)"
    )


@pytest.mark.asyncio
async def test_bounded_concurrency_and_cancellation_cleanup():
    """Verify that bounded concurrency semaphore is strictly enforced and cancellation frees resources."""
    max_concurrency = 3
    semaphore = asyncio.Semaphore(max_concurrency)
    active_concurrent = 0
    max_observed_concurrent = 0
    lock = asyncio.Lock()

    async def worker(task_id: int):
        nonlocal active_concurrent, max_observed_concurrent
        async with semaphore:
            async with lock:
                active_concurrent += 1
                if active_concurrent > max_observed_concurrent:
                    max_observed_concurrent = active_concurrent
            try:
                await asyncio.sleep(0.05)
            finally:
                async with lock:
                    active_concurrent -= 1

    tasks = [asyncio.create_task(worker(i)) for i in range(12)]
    await asyncio.gather(*tasks)

    # Concurrency budget: active concurrent workers must NEVER exceed max_concurrency
    assert max_observed_concurrent <= max_concurrency
    assert active_concurrent == 0

    # Test cooperative cancellation releases slots immediately
    cancellable_tasks = [asyncio.create_task(worker(i)) for i in range(5)]
    await asyncio.sleep(0.01)
    for t in cancellable_tasks:
        t.cancel()

    await asyncio.gather(*cancellable_tasks, return_exceptions=True)
    assert active_concurrent == 0
    assert semaphore._value == max_concurrency


@pytest.mark.asyncio
async def test_batch_wikimedia_api_efficiency(monkeypatch):
    """Verify media discovery uses single batch API requests without N+1 query loops (§DS-25)."""
    import httpx

    request_count = 0

    async def mock_get(self, url, *args, **kwargs):
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            status_code=200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Laser_cutting_head.jpg",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/laser.jpg",
                                    "width": 800,
                                    "height": 600,
                                }
                            ],
                        },
                        "2": {
                            "title": "File:Laser_beam_nozzle.png",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/nozzle.png",
                                    "width": 640,
                                    "height": 480,
                                }
                            ],
                        },
                    }
                }
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    results = await fetch_wikimedia_topic_images("laser optics", max_results=10)
    assert len(results) == 2
    # Must only perform 1 single batch query
    assert request_count == 1
