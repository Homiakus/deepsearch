"""Crawlee Batch Crawler Adapter (§5, DS-A15, DS-A16)."""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from scraper.config import settings, ExecutionMode
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import CapturedArtifact, AdaptiveAcquisitionEngine
from scraper.discovery.robots import robots_manager, RobotsDecision

logger = logging.getLogger(__name__)


class CrawleeBatchCrawler:
    """Bounded batch crawler using Crawlee request concurrency and adaptive acquisition."""

    def __init__(self, max_concurrency: int = 8, mode: ExecutionMode = ExecutionMode.BALANCED):
        self.max_concurrency = max_concurrency
        self.mode = mode
        self.engine = AdaptiveAcquisitionEngine()

    async def crawl_batch(self, urls: List[str], max_pages: int = 50) -> List[CapturedArtifact]:
        """Crawls a batch of seed URLs with concurrency bounds, robots checks, and deduplication."""
        semaphore = asyncio.Semaphore(self.max_concurrency)
        results: List[CapturedArtifact] = []
        seen_canonical = set()

        async def _fetch_one(url: str) -> Optional[CapturedArtifact]:
            c_url = canonicalize_url(url)
            if c_url in seen_canonical:
                return None
            seen_canonical.add(c_url)

            # Robots policy check (§22, DS-A13)
            allowed, decision = robots_manager.evaluate(url)
            if not allowed:
                logger.info("Skipping URL %s due to robots policy (%s)", url, decision.value)
                return None

            async with semaphore:
                try:
                    artifact = await self.engine.acquire_page(url, c_url, mode=self.mode)
                    return artifact
                except Exception as exc:
                    logger.warning("Error acquiring %s: %s", url, exc)
                    return None

        tasks = [_fetch_one(u) for u in urls[:max_pages]]
        batch_results = await asyncio.gather(*tasks)

        for res in batch_results:
            if res is not None:
                results.append(res)

        return results
