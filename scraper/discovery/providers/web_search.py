"""Generic Web / Open Search Provider (DS-SI08)."""

import logging
import urllib.parse
import httpx
from typing import List
from selectolax.parser import HTMLParser
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class WebSearchProvider:
    descriptor = ProviderDescriptor(
        name="web_search",
        supported_domains=[],
        supported_source_types=["OFFICIAL_DOC", "NEWS_MEDIA", "BLOG", "FORUM"],
        languages=["en", "ru"],
        freshness_capability="REALTIME",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        """Queries open web search endpoints (e.g. DuckDuckGo / SearXNG or HTML search fallback)."""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(request.query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        candidates = []
        try:
            async with httpx.AsyncClient(
                timeout=request.timeout_sec, trust_env=False
            ) as client:
                res = await client.get(url, headers=headers, follow_redirects=True)
                if res.status_code == 200 and res.text:
                    parser = HTMLParser(res.text)
                    for idx, a in enumerate(parser.css(".result__snippet"), start=1):
                        parent = a.parent
                        if parent:
                            title_a = parent.css_first(".result__title a")
                            if title_a:
                                href = title_a.attributes.get("href", "")
                                title_text = title_a.text(strip=True)
                                snippet_text = a.text(strip=True)
                                if href:
                                    if "uddg=" in href:
                                        qs = urllib.parse.parse_qs(
                                            urllib.parse.urlparse(href).query
                                        )
                                        target_url = qs.get("uddg", [None])[0]
                                        if target_url:
                                            href = urllib.parse.unquote(target_url)
                                    if (
                                        href.startswith("http")
                                        and "duckduckgo.com" not in href
                                    ):
                                        candidates.append(
                                            SourceCandidate(
                                                url=href,
                                                canonical_url=href,
                                                title=title_text,
                                                snippet=snippet_text[:300],
                                                provider=self.descriptor.name,
                                                provider_rank=idx,
                                                source_type="OFFICIAL_DOC",
                                                goal_ids=[request.goal_id]
                                                if request.goal_id
                                                else [],
                                                authority_prior=0.70,
                                            )
                                        )
                        if len(candidates) >= request.max_results:
                            break
        except Exception as exc:
            logger.warning(
                "WebSearchProvider search error for query '%s': %s", request.query, exc
            )

        return candidates
