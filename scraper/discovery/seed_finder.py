"""Multi-Source Seed Discovery Engine with Provider Registry Integration (DS-SI08, DS-SI82)."""

import logging
from typing import List, Optional

from scraper.discovery.providers.registry import provider_registry
from scraper.discovery.providers.base import ProviderSearchRequest
from scraper.research.intent import ResearchIntent
from scraper.research.query_normalizer import normalize_query
from scraper.research.entities import extract_entities_from_query
from scraper.research.decomposer import decompose_intent
from scraper.search.query_generator import QueryGenerator
from scraper.discovery.provider_policy import provider_policy

logger = logging.getLogger(__name__)


async def discover_diverse_seeds(
    query: str,
    domain: Optional[str] = None,
    preferred_sources: Optional[List[str]] = None,
    category: Optional[str] = None,
) -> List[str]:
    """Discovers diverse seed URLs using ProviderRegistry and QueryIntelligence."""
    discovered: List[str] = []

    # 1. Add user preferred sources first
    if preferred_sources:
        discovered.extend(preferred_sources)

    # 2. Build structured research intent & goal graph
    norm_q = normalize_query(query)
    entities = extract_entities_from_query(query)
    intent = ResearchIntent(
        original_query=query,
        normalized_query=norm_q.normalized_text,
        task_type=category or "general_research",
        domain=domain,
        entities=entities,
        languages=norm_q.detected_languages,
    )
    goal_graph = decompose_intent(intent)
    q_gen = QueryGenerator()
    query_variants = q_gen.generate_variants(intent, goal_graph)

    # 3. Plan provider requests using ProviderPolicy
    provider_reqs = []
    for goal in goal_graph.goals.values():
        reqs = provider_policy.plan_provider_requests(intent, goal, query_variants)
        provider_reqs.extend(reqs)

    # 4. Parallel search via provider registry
    candidates = await provider_registry.search_parallel(provider_reqs)

    for c in candidates:
        if c.url and c.url not in discovered:
            discovered.append(c.url)

    # Fallback to direct provider lookups if parallel candidates empty
    if not discovered:
        p_wiki = provider_registry.get("wikipedia")
        if p_wiki:
            wiki_candidates = await p_wiki.search(
                ProviderSearchRequest(query=query, max_results=3, language="en")
            )
            discovered.extend(
                [c.url for c in wiki_candidates if c.url not in discovered]
            )

    # Deduplicate while preserving order
    seen = set()
    final_seeds = []
    for u in discovered:
        if u not in seen:
            seen.add(u)
            final_seeds.append(u)

    logger.info(
        "Discovered %d diverse seed URLs for query '%s'", len(final_seeds), query
    )
    return final_seeds


# Backward compatibility helper functions
async def fetch_arxiv_seeds(query: str, max_results: int = 5) -> List[str]:
    p = provider_registry.get("arxiv")
    if p:
        candidates = await p.search(
            ProviderSearchRequest(query=query, max_results=max_results)
        )
        return [c.url for c in candidates]
    return []


async def fetch_wikipedia_search_seeds(
    query: str, lang: str = "en", max_results: int = 5
) -> List[str]:
    p = provider_registry.get("wikipedia")
    if p:
        candidates = await p.search(
            ProviderSearchRequest(query=query, max_results=max_results, language=lang)
        )
        return [c.url for c in candidates]
    return []


async def fetch_europe_pmc_seeds(query: str, max_results: int = 5) -> List[str]:
    p = provider_registry.get("europe_pmc")
    if p:
        candidates = await p.search(
            ProviderSearchRequest(query=query, max_results=max_results)
        )
        return [c.url for c in candidates]
    return []


async def fetch_pubmed_seeds(query: str, max_results: int = 5) -> List[str]:
    p = provider_registry.get("pubmed")
    if p:
        candidates = await p.search(
            ProviderSearchRequest(query=query, max_results=max_results)
        )
        return [c.url for c in candidates]
    return []


async def fetch_annas_archive_seeds(query: str, max_results: int = 5) -> List[str]:
    p = provider_registry.get("annas_archive")
    if p:
        candidates = await p.search(
            ProviderSearchRequest(query=query, max_results=max_results)
        )
        return [c.url for c in candidates]
    return []
