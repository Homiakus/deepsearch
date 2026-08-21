"""Europe PMC Discovery Provider (DS-SI08)."""

import logging
import urllib.parse
import httpx
from typing import List
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class EuropePMCProvider:
    descriptor = ProviderDescriptor(
        name="europe_pmc",
        supported_domains=["europepmc.org"],
        supported_source_types=["PRIMARY_RESEARCH", "SYSTEMATIC_REVIEW", "GUIDELINE"],
        languages=["en"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(request.query)}&format=json&pageSize={request.max_results}"
        candidates = []
        try:
            transport = httpx.AsyncHTTPTransport(retries=2)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    results = data.get("resultList", {}).get("result", [])
                    for idx, item in enumerate(results, start=1):
                        pmcid = item.get("pmcid")
                        pmid = item.get("pmid")
                        doi = item.get("doi")
                        title = item.get("title", "")
                        abstract = item.get("abstractText", "")
                        pub_year = str(item.get("pubYear", ""))

                        target_url = None
                        if pmcid:
                            target_url = f"https://europepmc.org/article/PMC/{pmcid}"
                        elif pmid:
                            target_url = f"https://europepmc.org/abstract/MED/{pmid}"
                        elif doi:
                            target_url = f"https://doi.org/{doi}"

                        if target_url:
                            candidates.append(
                                SourceCandidate(
                                    url=target_url,
                                    canonical_url=target_url,
                                    title=title,
                                    snippet=abstract[:300],
                                    provider=self.descriptor.name,
                                    provider_rank=idx,
                                    source_type="PRIMARY_RESEARCH",
                                    published_at=pub_year or None,
                                    goal_ids=[request.goal_id]
                                    if request.goal_id
                                    else [],
                                    authority_prior=0.95,
                                    provider_metadata={
                                        "pmcid": pmcid or "",
                                        "pmid": pmid or "",
                                        "doi": doi or "",
                                    },
                                )
                            )
        except Exception as exc:
            logger.warning(
                "EuropePMCProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
