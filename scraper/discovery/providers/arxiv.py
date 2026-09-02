"""ArXiv Discovery Provider (DS-SI08)."""

import logging
import urllib.parse
import xml.etree.ElementTree as ET

import httpx

from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class ArxivProvider:
    descriptor = ProviderDescriptor(
        name="arxiv",
        supported_domains=["export.arxiv.org", "arxiv.org"],
        supported_source_types=["PRIMARY_RESEARCH"],
        languages=["en"],
        freshness_capability="HIGH",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]:
        url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(request.query)}&start=0&max_results={request.max_results}"
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
                    root = ET.fromstring(res.text)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    for idx, entry in enumerate(
                        root.findall("atom:entry", ns), start=1
                    ):
                        id_elem = entry.find("atom:id", ns)
                        title_elem = entry.find("atom:title", ns)
                        summary_elem = entry.find("atom:summary", ns)
                        pub_elem = entry.find("atom:published", ns)

                        link = (
                            id_elem.text.strip()
                            if id_elem is not None and id_elem.text
                            else ""
                        )
                        title = (
                            " ".join(title_elem.text.split())
                            if title_elem is not None and title_elem.text
                            else ""
                        )
                        summary = (
                            " ".join(summary_elem.text.split())
                            if summary_elem is not None and summary_elem.text
                            else ""
                        )
                        pub_date = (
                            pub_elem.text.strip()
                            if pub_elem is not None and pub_elem.text
                            else None
                        )

                        if link:
                            candidates.append(
                                SourceCandidate(
                                    url=link,
                                    canonical_url=link,
                                    title=title,
                                    snippet=summary[:300],
                                    provider=self.descriptor.name,
                                    provider_rank=idx,
                                    source_type="PRIMARY_RESEARCH",
                                    published_at=pub_date,
                                    goal_ids=[request.goal_id]
                                    if request.goal_id
                                    else [],
                                    authority_prior=0.90,
                                )
                            )
        except Exception as exc:
            logger.warning(
                "ArxivProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
