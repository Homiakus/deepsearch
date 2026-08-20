"""Wikipedia Discovery Provider (DS-SI08)."""

import logging
import urllib.parse
import httpx
from typing import List
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class WikipediaProvider:
    descriptor = ProviderDescriptor(
        name="wikipedia",
        supported_domains=["wikipedia.org", "en.wikipedia.org", "ru.wikipedia.org"],
        supported_source_types=["WIKI"],
        languages=["en", "ru"],
        freshness_capability="ARCHIVAL",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        lang = request.language if request.language in ("en", "ru") else "en"
        url = f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(request.query)}&limit={request.max_results}&namespace=0&format=json"
        candidates = []
        headers = {
            "User-Agent": "DeepSearchBot/1.0 (https://github.com/deepsearch; contact@deepsearch.org) Mozilla/5.0"
        }
        try:
            async with httpx.AsyncClient(
                timeout=request.timeout_sec, trust_env=False
            ) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    titles = (
                        data[1] if len(data) > 1 and isinstance(data[1], list) else []
                    )
                    snippets = (
                        data[2] if len(data) > 2 and isinstance(data[2], list) else []
                    )
                    urls = (
                        data[3] if len(data) > 3 and isinstance(data[3], list) else []
                    )

                    for idx, link in enumerate(urls, start=1):
                        title = titles[idx - 1] if idx - 1 < len(titles) else ""
                        snippet = snippets[idx - 1] if idx - 1 < len(snippets) else ""
                        candidates.append(
                            SourceCandidate(
                                url=link,
                                canonical_url=link,
                                title=title,
                                snippet=snippet,
                                provider=self.descriptor.name,
                                provider_rank=idx,
                                source_type="WIKI",
                                goal_ids=[request.goal_id] if request.goal_id else [],
                                authority_prior=0.75,
                            )
                        )
        except Exception as exc:
            logger.warning(
                "WikipediaProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
