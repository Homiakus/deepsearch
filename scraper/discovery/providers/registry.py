"""Discovery Provider Registry & Parallel Search Runner (DS-SI08, DS-SI09)."""

import asyncio
import logging
from typing import Dict, List, Optional
from scraper.discovery.providers.base import DiscoveryProvider, ProviderDescriptor, ProviderSearchRequest
from scraper.discovery.providers.wikipedia import WikipediaProvider
from scraper.discovery.providers.arxiv import ArxivProvider
from scraper.discovery.providers.europe_pmc import EuropePMCProvider
from scraper.discovery.providers.pubmed import PubMedProvider
from scraper.discovery.providers.github import GitHubProvider
from scraper.discovery.providers.annas_archive import AnnasArchiveProvider
from scraper.discovery.providers.web_search import WebSearchProvider
from scraper.search.candidates import SourceCandidate
from scraper.search.trace import SearchTrace, TraceEventType

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Central registry of discovery providers with bounded parallel execution."""

    def __init__(self):
        self._providers: Dict[str, DiscoveryProvider] = {}
        # Register standard default providers
        self.register(WikipediaProvider())
        self.register(ArxivProvider())
        self.register(EuropePMCProvider())
        self.register(PubMedProvider())
        self.register(GitHubProvider())
        self.register(AnnasArchiveProvider())
        self.register(WebSearchProvider())

    def register(self, provider: DiscoveryProvider):
        self._providers[provider.descriptor.name] = provider

    def get(self, name: str) -> Optional[DiscoveryProvider]:
        return self._providers.get(name)

    def list_all(self) -> List[DiscoveryProvider]:
        return list(self._providers.values())

    async def search_parallel(
        self,
        requests: List[tuple[DiscoveryProvider, ProviderSearchRequest]],
        max_concurrency: int = 5,
        trace: Optional[SearchTrace] = None,
    ) -> List[SourceCandidate]:
        """Executes provider requests in parallel with bounded concurrency and trace logging (DS-SI09)."""
        semaphore = asyncio.Semaphore(max_concurrency)
        candidates: List[SourceCandidate] = []

        async def _run_single(provider: DiscoveryProvider, req: ProviderSearchRequest):
            async with semaphore:
                if trace:
                    trace.record(
                        event_type=TraceEventType.PROVIDER_CALLED,
                        entity_id=provider.descriptor.name,
                        stage="discovery",
                        metadata={"query": req.query, "goal_id": req.goal_id or ""},
                    )
                try:
                    results = await asyncio.wait_for(provider.search(req), timeout=req.timeout_sec)
                    for c in results:
                        if trace:
                            trace.record(
                                event_type=TraceEventType.CANDIDATE_DISCOVERED,
                                entity_id=c.url,
                                stage="discovery",
                                decision="DISCOVERED",
                                metadata={"provider": provider.descriptor.name, "goal_id": req.goal_id or ""},
                            )
                    return results
                except Exception as exc:
                    logger.warning("Provider %s failed for query '%s': %s", provider.descriptor.name, req.query, exc)
                    return []

        tasks = [_run_single(p, r) for p, r in requests]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in batch_results:
            if isinstance(res, list):
                candidates.extend(res)

        return candidates


provider_registry = ProviderRegistry()
