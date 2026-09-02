"""Browser Acquisition Baseline Runner (DS-RB00).

Measures baseline latency, memory, status, content bytes, useful text, links count, and quality score.
"""

import asyncio
import logging
import os
import time
from typing import Any

import psutil
import yaml

from scraper.acquisition.http_fetcher import HTTPFetcher
from scraper.acquisition.page_classifier import classify_page

logger = logging.getLogger("browser_baseline")


async def measure_url_acquisition(url: str, fetcher: HTTPFetcher) -> dict[str, Any]:
    proc = psutil.Process(os.getpid())
    rss_before = proc.memory_info().rss / (1024 * 1024)
    t0 = time.perf_counter()

    result: dict[str, Any] = {
        "url": url,
        "success": False,
        "status_code": 0,
        "final_url": url,
        "content_bytes": 0,
        "useful_text_chars": 0,
        "links_count": 0,
        "screenshot_valid": False,
        "network_requests": 1,
        "elapsed_ms": 0.0,
        "cpu_time_ms": 0.0,
        "rss_peak_mb": rss_before,
        "quality_score": 0.0,
        "failure_class": None,
    }

    try:
        res = await fetcher.fetch(url, timeout=15.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        rss_after = proc.memory_info().rss / (1024 * 1024)

        result["success"] = res.status_code < 400
        result["status_code"] = res.status_code
        result["final_url"] = res.url
        result["content_bytes"] = len(res.content)
        result["useful_text_chars"] = len(res.text.strip())
        result["elapsed_ms"] = elapsed_ms
        result["rss_peak_mb"] = max(rss_before, rss_after)

        pi = classify_page(res.url, res.status_code, res.headers, res.text)
        result["quality_score"] = max(0.0, 1.0 - pi.block_score)
        result["links_count"] = len(pi.detected_apis)

    except Exception as exc:
        result["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        result["failure_class"] = type(exc).__name__

    return result


async def run_baseline(corpus_path: str, max_items: int = 50) -> list[dict[str, Any]]:
    if not os.path.exists(corpus_path):
        logger.error("Corpus file not found: %s", corpus_path)
        return []

    with open(corpus_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    urls: list[str] = []
    for cat in data.get("categories", []):
        for item in cat.get("items", []):
            if not item.get("should_block"):
                urls.append(item["url"])

    urls = urls[:max_items]
    fetcher = HTTPFetcher()
    results = []

    print(f"Running baseline benchmark across {len(urls)} URLs...")
    for u in urls:
        r = await measure_url_acquisition(u, fetcher)
        results.append(r)
        print(
            f"  [{r['status_code']}] {r['url']} -> {r['elapsed_ms']:.1f}ms (quality: {r['quality_score']:.2f})"
        )

    await fetcher.close()
    return results


if __name__ == "__main__":
    corpus_file = os.path.join(os.path.dirname(__file__), "corpus.yaml")
    results = asyncio.run(run_baseline(corpus_file, max_items=20))
    print(f"Baseline completed: {len(results)} pages benchmarked.")
