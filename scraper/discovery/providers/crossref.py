"""CrossRef Official Scientific DOI Discovery Provider (DS-SI08).

Queries official CrossRef REST API for verified peer-reviewed publications,
DOIs, publishers (Springer, Elsevier, Wiley, Nature, IEEE), and citation metrics.
"""

import logging
import urllib.parse
import httpx
from typing import List
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class CrossRefProvider:
    descriptor = ProviderDescriptor(
        name="crossref",
        supported_domains=["api.crossref.org", "doi.org"],
        supported_source_types=[
            "PRIMARY_RESEARCH",
            "SYSTEMATIC_REVIEW",
            "BOOK_CHAPTER",
        ],
        languages=["en", "ru", "zh", "fr", "de", "es"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        query_encoded = urllib.parse.quote(request.query)
        select_fields = "DOI,title,abstract,author,published,container-title,is-referenced-by-count,link,type"
        url = f"https://api.crossref.org/works?query={query_encoded}&rows={request.max_results}&select={select_fields}"

        candidates = []
        try:
            headers = {
                "User-Agent": "DeepSearch-Research/1.0 (mailto:scholar@deepsearch.ai)"
            }
            async with httpx.AsyncClient(
                timeout=request.timeout_sec, headers=headers, trust_env=False
            ) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    items = data.get("message", {}).get("items", [])
                    for idx, item in enumerate(items, start=1):
                        doi = item.get("DOI")
                        if not doi:
                            continue

                        titles = item.get("title", [])
                        title = titles[0] if titles else "Scientific Publication"
                        abstract = item.get("abstract", "") or ""
                        # Strip simple XML tags in CrossRef abstracts like <jats:p>
                        import re

                        clean_abstract = re.sub(r"<[^>]+>", "", abstract).strip()

                        citations = item.get("is-referenced-by-count", 0) or 0
                        containers = item.get("container-title", [])
                        journal = containers[0] if containers else ""
                        pub_type = item.get("type", "journal-article")

                        pub_parts = item.get("published", {}).get("date-parts", [[]])[0]
                        pub_year = str(pub_parts[0]) if pub_parts else None

                        target_url = f"https://doi.org/{doi}"

                        auth_prior = 0.94
                        if citations > 50:
                            auth_prior = 0.98

                        source_type = "PRIMARY_RESEARCH"
                        if "review" in pub_type.lower() or "review" in title.lower():
                            source_type = "SYSTEMATIC_REVIEW"
                        elif (
                            "book" in pub_type.lower() or "chapter" in pub_type.lower()
                        ):
                            source_type = "BOOK_CHAPTER"

                        snippet = clean_abstract[:350]
                        if journal:
                            snippet = f"[{journal}, {pub_year or ''}] " + snippet

                        candidates.append(
                            SourceCandidate(
                                url=target_url,
                                canonical_url=target_url,
                                title=title,
                                snippet=snippet,
                                provider=self.descriptor.name,
                                provider_rank=idx,
                                source_type=source_type,
                                published_at=pub_year,
                                goal_ids=[request.goal_id] if request.goal_id else [],
                                authority_prior=auth_prior,
                                provider_metadata={
                                    "doi": doi,
                                    "journal": journal,
                                    "citations": citations,
                                    "pub_type": pub_type,
                                },
                            )
                        )
        except Exception as exc:
            logger.warning(
                "CrossRefProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
