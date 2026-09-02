"""Discovery Provider Registry & Parallel Search Runner (DS-SI08, DS-SI09)."""

import asyncio
import logging
import time
import urllib.parse

from scraper.config import settings
from scraper.discovery.providers.annas_archive import AnnasArchiveProvider
from scraper.discovery.providers.arxiv import ArxivProvider
from scraper.discovery.providers.base import (
    DiscoveryProvider,
    ProviderExecutionReport,
    ProviderSearchRequest,
    ProviderStatus,
)
from scraper.discovery.providers.crossref import CrossRefProvider
from scraper.discovery.providers.europe_pmc import EuropePMCProvider
from scraper.discovery.providers.github import GitHubProvider
from scraper.discovery.providers.keenable import KeenableSearchProvider
from scraper.discovery.providers.openalex import OpenAlexProvider
from scraper.discovery.providers.pubmed import PubMedProvider
from scraper.discovery.providers.regional_academic import RegionalAcademicProvider
from scraper.discovery.providers.semantic_scholar import SemanticScholarProvider
from scraper.discovery.providers.web_search import WebSearchProvider
from scraper.discovery.providers.wikipedia import WikipediaProvider
from scraper.search.candidates import SourceCandidate
from scraper.search.trace import SearchTrace, TraceEventType

logger = logging.getLogger(__name__)


def is_matching_domain(url: str, domain: str | None) -> bool:
    """Verifies that URL matches target domain hostname, rejecting substring collisions (DS-13)."""
    if not domain:
        return True
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        target = domain.lower().strip()
        return host == target or host.endswith("." + target)
    except Exception:
        return False


class ProviderRegistry:
    """Central registry of discovery providers with bounded parallel execution (DS-13)."""

    def __init__(self):
        self._providers: dict[str, DiscoveryProvider] = {}
        # Register standard default providers
        self.register(KeenableSearchProvider())
        self.register(WikipediaProvider())
        self.register(ArxivProvider())
        self.register(EuropePMCProvider())
        self.register(PubMedProvider())
        self.register(SemanticScholarProvider())
        self.register(OpenAlexProvider())
        self.register(CrossRefProvider())
        self.register(RegionalAcademicProvider())
        self.register(GitHubProvider())
        self.register(AnnasArchiveProvider())
        self.register(WebSearchProvider())

    def register(self, provider: DiscoveryProvider):
        self._providers[provider.descriptor.name] = provider

    def get(self, name: str) -> DiscoveryProvider | None:
        return self._providers.get(name)

    def list_all(self) -> list[DiscoveryProvider]:
        return list(self._providers.values())

    async def search_parallel_with_reports(
        self,
        requests: list[tuple[DiscoveryProvider, ProviderSearchRequest]],
        max_concurrency: int = 5,
        trace: SearchTrace | None = None,
        domain: str | None = None,
        include_opt_in: bool = False,
    ) -> tuple[list[SourceCandidate], list[ProviderExecutionReport]]:
        """Executes provider requests in parallel with bounded concurrency, returning merged candidates and reports (DS-13)."""
        semaphore = asyncio.Semaphore(max_concurrency)
        reports: list[ProviderExecutionReport] = []

        allow_annas = include_opt_in or getattr(settings, "enable_annas_archive", False)

        valid_requests: list[tuple[int, DiscoveryProvider, ProviderSearchRequest]] = []
        for idx, (provider, req) in enumerate(requests):
            if provider.descriptor.opt_in_only and not allow_annas:
                reports.append(
                    ProviderExecutionReport(
                        provider_name=provider.descriptor.name,
                        status=ProviderStatus.SKIPPED,
                        candidate_count=0,
                        latency_sec=0.0,
                        error="Opt-in required",
                    )
                )
                continue
            valid_requests.append((idx, provider, req))

        async def _run_single(
            req_idx: int, provider: DiscoveryProvider, req: ProviderSearchRequest
        ) -> tuple[int, list[SourceCandidate], ProviderExecutionReport]:
            p_name = provider.descriptor.name
            start_t = time.perf_counter()
            async with semaphore:
                if trace:
                    trace.record(
                        event_type=TraceEventType.PROVIDER_CALLED,
                        entity_id=p_name,
                        stage="discovery",
                        metadata={"query": req.query, "goal_id": req.goal_id or ""},
                    )
                try:
                    results = await asyncio.wait_for(
                        provider.search(req), timeout=req.timeout_sec
                    )
                    elapsed = time.perf_counter() - start_t
                    report = ProviderExecutionReport(
                        provider_name=p_name,
                        status=ProviderStatus.SUCCESS,
                        candidate_count=len(results),
                        latency_sec=round(elapsed, 4),
                    )
                    if trace:
                        for c in results:
                            trace.record(
                                event_type=TraceEventType.CANDIDATE_DISCOVERED,
                                entity_id=c.url,
                                stage="discovery",
                                decision="DISCOVERED",
                                metadata={
                                    "provider": p_name,
                                    "goal_id": req.goal_id or "",
                                },
                            )
                    return req_idx, results, report
                except TimeoutError:
                    elapsed = time.perf_counter() - start_t
                    logger.warning(
                        "Provider %s timed out after %.2fs", p_name, req.timeout_sec
                    )
                    report = ProviderExecutionReport(
                        provider_name=p_name,
                        status=ProviderStatus.TIMEOUT,
                        candidate_count=0,
                        latency_sec=round(elapsed, 4),
                        error=f"Timeout after {req.timeout_sec}s",
                    )
                    return req_idx, [], report
                except Exception as exc:
                    elapsed = time.perf_counter() - start_t
                    logger.warning(
                        "Provider %s failed for query '%s': %s", p_name, req.query, exc
                    )
                    report = ProviderExecutionReport(
                        provider_name=p_name,
                        status=ProviderStatus.FAILED,
                        candidate_count=0,
                        latency_sec=round(elapsed, 4),
                        error=str(exc),
                    )
                    return req_idx, [], report

        tasks = [_run_single(idx, p, r) for idx, p, r in valid_requests]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Sort results deterministically by original request index
        ordered_results: list[
            tuple[int, list[SourceCandidate], ProviderExecutionReport]
        ] = []
        for item in batch_results:
            if isinstance(item, tuple) and len(item) == 3:
                ordered_results.append(item)
                reports.append(item[2])
            elif isinstance(item, Exception):
                logger.error("Unexpected error in search_parallel: %s", item)

        ordered_results.sort(key=lambda x: x[0])

        # Merge and deduplicate candidates deterministically
        candidates: list[SourceCandidate] = []
        seen_urls: set[str] = set()

        for _, cand_list, _ in ordered_results:
            for c in cand_list:
                if not c.url or c.url in seen_urls:
                    continue
                if domain and not is_matching_domain(c.url, domain):
                    continue
                seen_urls.add(c.url)
                candidates.append(c)

        return candidates, reports

    async def search_parallel(
        self,
        requests: list[tuple[DiscoveryProvider, ProviderSearchRequest]],
        max_concurrency: int = 5,
        trace: SearchTrace | None = None,
        domain: str | None = None,
        include_opt_in: bool = False,
    ) -> list[SourceCandidate]:
        """Executes provider requests in parallel with bounded concurrency and trace logging (DS-13)."""
        candidates, _ = await self.search_parallel_with_reports(
            requests=requests,
            max_concurrency=max_concurrency,
            trace=trace,
            domain=domain,
            include_opt_in=include_opt_in,
        )
        return candidates


provider_registry = ProviderRegistry()
