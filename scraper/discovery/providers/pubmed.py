"""PubMed NCBI Discovery Provider (DS-SI08)."""

import logging
import urllib.parse

import httpx

from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class PubMedProvider:
    descriptor = ProviderDescriptor(
        name="pubmed",
        supported_domains=["pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov"],
        supported_source_types=["PRIMARY_RESEARCH", "SYSTEMATIC_REVIEW", "GUIDELINE"],
        languages=["en"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]:
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term={urllib.parse.quote(request.query)}&retmode=json&retmax={request.max_results}"
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
                    id_list = data.get("esearchresult", {}).get("idlist", [])
                    for idx, pmc_id in enumerate(id_list, start=1):
                        target_url = f"https://europepmc.org/article/PMC/PMC{pmc_id}"
                        candidates.append(
                            SourceCandidate(
                                url=target_url,
                                canonical_url=target_url,
                                title=f"NCBI PMC Article {pmc_id}",
                                snippet="",
                                provider=self.descriptor.name,
                                provider_rank=idx,
                                source_type="PRIMARY_RESEARCH",
                                goal_ids=[request.goal_id] if request.goal_id else [],
                                authority_prior=0.95,
                                provider_metadata={"pmc_id": pmc_id},
                            )
                        )
        except Exception as exc:
            logger.warning(
                "PubMedProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
