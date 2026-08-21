"""GitHub & Code Repositories Discovery Provider (DS-SI08)."""

import logging
import urllib.parse
import httpx
from typing import List
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class GitHubProvider:
    descriptor = ProviderDescriptor(
        name="github",
        supported_domains=["github.com"],
        supported_source_types=["SOURCE_CODE", "OFFICIAL_DOC"],
        languages=["en"],
        freshness_capability="REALTIME",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(request.query)}&sort=stars&order=desc&per_page={request.max_results}"
        headers = {"User-Agent": "DeepSearch-Research-Bot"}
        candidates = []
        try:
            transport = httpx.AsyncHTTPTransport(retries=2)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    items = data.get("items", [])
                    for idx, repo in enumerate(items, start=1):
                        html_url = repo.get("html_url", "")
                        desc = repo.get("description", "") or ""
                        full_name = repo.get("full_name", "")
                        if html_url:
                            candidates.append(
                                SourceCandidate(
                                    url=html_url,
                                    canonical_url=html_url,
                                    title=f"GitHub: {full_name}",
                                    snippet=desc[:300],
                                    provider=self.descriptor.name,
                                    provider_rank=idx,
                                    source_type="SOURCE_CODE",
                                    goal_ids=[request.goal_id]
                                    if request.goal_id
                                    else [],
                                    authority_prior=0.90,
                                )
                            )
        except Exception as exc:
            logger.warning(
                "GitHubProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
