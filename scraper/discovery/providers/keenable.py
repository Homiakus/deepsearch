"""Keenable Web Search and AI Retrieval Discovery Provider (DS-SI08, DS-13).

Integrates Keenable.ai 100B+ web index with keyless public tier (1000 req/hr)
and authenticated Pro search with real-time freshness.
"""

import logging
import os
from typing import Any

import httpx

from scraper.config import settings
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class KeenableSearchProvider:
    """Discovery provider using Keenable AI Search API."""

    descriptor = ProviderDescriptor(
        name="keenable",
        supported_domains=[],
        supported_source_types=[
            "PRIMARY_RESEARCH",
            "OFFICIAL_DOC",
            "NEWS_MEDIA",
            "BLOG",
        ],
        languages=["en", "ru", "de", "fr", "es", "zh", "ja"],
        freshness_capability="REALTIME",
        cost_class="FREE",
    )

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = (
            api_key
            or getattr(settings, "keenable_api_key", None)
            or os.environ.get("KEENABLE_API_KEY")
        )
        self.base_url = (
            base_url or getattr(settings, "keenable_api_url", "https://api.keenable.ai")
        ).rstrip("/")

    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]:
        """Queries Keenable Search API (public keyless or authenticated endpoint)."""
        is_authenticated = bool(self.api_key)
        endpoint = (
            f"{self.base_url}/v1/search"
            if is_authenticated
            else f"{self.base_url}/v1/search/public"
        )

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DeepSearch-Platform/1.0",
            "X-Keenable-Title": "DeepSearch",
        }
        if is_authenticated:
            headers["X-API-Key"] = self.api_key

        payload: dict[str, Any] = {
            "query": request.query,
            "mode": "pro",
        }

        candidates: list[SourceCandidate] = []
        try:
            transport = httpx.AsyncHTTPTransport(retries=2)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    results = data.get("results", [])
                    if isinstance(results, list):
                        for idx, item in enumerate(results, start=1):
                            url = item.get("url")
                            if not url or not url.startswith("http"):
                                continue

                            title = item.get("title") or url
                            snippet = (
                                item.get("snippet") or item.get("description") or ""
                            )

                            candidate = SourceCandidate(
                                url=url,
                                canonical_url=url,
                                title=title,
                                snippet=snippet[:400],
                                provider=self.descriptor.name,
                                provider_rank=idx,
                                source_type="PRIMARY_RESEARCH"
                                if any(
                                    kw in url
                                    for kw in (
                                        "arxiv",
                                        "doi.org",
                                        "nature",
                                        "science",
                                        "acm",
                                        "ieee",
                                        "springer",
                                    )
                                )
                                else "OFFICIAL_DOC",
                                goal_ids=[request.goal_id] if request.goal_id else [],
                                authority_prior=0.85,
                            )
                            candidates.append(candidate)
                            if len(candidates) >= request.max_results:
                                break
                else:
                    logger.warning(
                        "Keenable search API returned status %d for query '%s': %s",
                        res.status_code,
                        request.query,
                        res.text[:200],
                    )
        except Exception as exc:
            logger.warning(
                "Keenable search error for query '%s': %s", request.query, exc
            )

        return candidates
