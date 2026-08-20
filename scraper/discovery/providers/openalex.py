"""OpenAlex Global Academic Discovery Provider (DS-SI08).

Queries OpenAlex catalog (250M+ scientific publications, full citation graphs,
authors, institutions, concepts, and open access full-text URLs).
"""

import logging
import urllib.parse
import httpx
from typing import List, Dict
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class OpenAlexProvider:
    descriptor = ProviderDescriptor(
        name="openalex",
        supported_domains=["openalex.org", "api.openalex.org"],
        supported_source_types=["PRIMARY_RESEARCH", "SYSTEMATIC_REVIEW", "DATASET"],
        languages=["en", "ru", "zh", "es", "fr", "de"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    @staticmethod
    def _reconstruct_abstract(inverted_index: Dict[str, List[int]]) -> str:
        if not inverted_index:
            return ""
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        query_encoded = urllib.parse.quote(request.query)
        select_fields = "id,doi,title,abstract_inverted_index,publication_year,cited_by_count,primary_location,open_access,type"
        url = f"https://api.openalex.org/works?search={query_encoded}&per_page={request.max_results}&select={select_fields}"

        candidates = []
        try:
            headers = {
                "User-Agent": "DeepSearch-Academic-Engine/1.0 (mailto:research@deepsearch.ai)"
            }
            async with httpx.AsyncClient(
                timeout=request.timeout_sec, headers=headers, trust_env=False
            ) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    works = data.get("results", [])
                    for idx, work in enumerate(works, start=1):
                        work_id = work.get("id", "")
                        doi = work.get("doi")
                        title = work.get("title", "") or "Scientific Work"
                        pub_year = work.get("publication_year")
                        citations = work.get("cited_by_count", 0) or 0
                        work_type = work.get("type", "article") or "article"

                        # Reconstruct abstract from inverted index
                        inv_index = work.get("abstract_inverted_index") or {}
                        abstract = self._reconstruct_abstract(inv_index)

                        # Open access & full text landing
                        oa_info = work.get("open_access") or {}
                        oa_url = oa_info.get("oa_url")
                        primary_loc = work.get("primary_location") or {}
                        landing_page_url = primary_loc.get("landing_page_url")

                        target_url = doi or oa_url or landing_page_url or work_id
                        if not target_url:
                            continue

                        # Prior based on peer-review & citations
                        auth_prior = 0.93
                        if citations > 150:
                            auth_prior = 0.99
                        elif citations > 30:
                            auth_prior = 0.95

                        source_type = "PRIMARY_RESEARCH"
                        if "review" in work_type.lower() or "review" in title.lower():
                            source_type = "SYSTEMATIC_REVIEW"
                        elif "dataset" in work_type.lower():
                            source_type = "DATASET"

                        snippet = (
                            abstract[:350]
                            if abstract
                            else f"Published in {pub_year or 'N/A'}, Cited by {citations} researchers."
                        )

                        candidates.append(
                            SourceCandidate(
                                url=target_url,
                                canonical_url=target_url,
                                title=title,
                                snippet=snippet,
                                provider=self.descriptor.name,
                                provider_rank=idx,
                                source_type=source_type,
                                published_at=str(pub_year) if pub_year else None,
                                goal_ids=[request.goal_id] if request.goal_id else [],
                                authority_prior=auth_prior,
                                provider_metadata={
                                    "openalex_id": work_id,
                                    "doi": doi or "",
                                    "citations": citations,
                                    "is_oa": oa_info.get("is_oa", False),
                                    "pdf_url": oa_url or "",
                                },
                            )
                        )
        except Exception as exc:
            logger.warning(
                "OpenAlexProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
