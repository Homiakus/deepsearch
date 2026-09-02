"""Generic Web / Open Search Provider with Multi-Endpoint Fallback (DS-SI08)."""

import logging
import urllib.parse

import httpx
from selectolax.parser import HTMLParser

from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)

BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


class WebSearchProvider:
    descriptor = ProviderDescriptor(
        name="web_search",
        supported_domains=[],
        supported_source_types=["OFFICIAL_DOC", "NEWS_MEDIA", "BLOG", "FORUM"],
        languages=["en", "ru"],
        freshness_capability="REALTIME",
        cost_class="FREE",
    )

    def _extract_target_url(self, raw_href: str) -> str:
        """Extract clean target URL from redirect wrappers (uddg= or r.html)."""
        if not raw_href:
            return ""
        if "uddg=" in raw_href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
            target = qs.get("uddg", [None])[0]
            if target:
                return urllib.parse.unquote(target)
        if raw_href.startswith("//"):
            return f"https:{raw_href}"
        return raw_href

    def _parse_ddg_html(
        self, html_text: str, request: ProviderSearchRequest
    ) -> list[SourceCandidate]:
        """Parse standard DuckDuckGo HTML output."""
        candidates: list[SourceCandidate] = []
        parser = HTMLParser(html_text)

        for idx, snippet_node in enumerate(parser.css(".result__snippet"), start=1):
            parent = snippet_node.parent
            if not parent:
                continue
            title_node = parent.css_first(".result__title a")
            if not title_node:
                continue

            raw_href = title_node.attributes.get("href", "")
            clean_url = self._extract_target_url(raw_href)
            title_text = title_node.text(strip=True)
            snippet_text = snippet_node.text(strip=True)

            if clean_url.startswith("http") and "duckduckgo.com" not in clean_url:
                candidates.append(
                    SourceCandidate(
                        url=clean_url,
                        canonical_url=clean_url,
                        title=title_text,
                        snippet=snippet_text[:300],
                        provider=self.descriptor.name,
                        provider_rank=idx,
                        source_type="OFFICIAL_DOC",
                        goal_ids=[request.goal_id] if request.goal_id else [],
                        authority_prior=0.70,
                    )
                )
            if len(candidates) >= request.max_results:
                break
        return candidates

    def _parse_ddg_lite(
        self, html_text: str, request: ProviderSearchRequest
    ) -> list[SourceCandidate]:
        """Parse DuckDuckGo Lite output (table-based format, highly anti-bot resilient)."""
        candidates: list[SourceCandidate] = []
        parser = HTMLParser(html_text)

        links = parser.css("a.result-link")
        snippets = parser.css("td.result-snippet")

        for idx, link_node in enumerate(links, start=1):
            raw_href = link_node.attributes.get("href", "")
            clean_url = self._extract_target_url(raw_href)
            title_text = link_node.text(strip=True)
            snippet_text = (
                snippets[idx - 1].text(strip=True) if idx - 1 < len(snippets) else ""
            )

            if clean_url.startswith("http") and "duckduckgo.com" not in clean_url:
                candidates.append(
                    SourceCandidate(
                        url=clean_url,
                        canonical_url=clean_url,
                        title=title_text,
                        snippet=snippet_text[:300],
                        provider=self.descriptor.name,
                        provider_rank=idx,
                        source_type="OFFICIAL_DOC",
                        goal_ids=[request.goal_id] if request.goal_id else [],
                        authority_prior=0.70,
                    )
                )
            if len(candidates) >= request.max_results:
                break
        return candidates

    async def search(self, request: ProviderSearchRequest) -> list[SourceCandidate]:
        """Queries open web search endpoints with multi-tier fallback (DDG HTML -> DDG Lite)."""
        headers = {
            "User-Agent": BROWSER_USER_AGENTS[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        }

        # 1. Primary: DDG HTML Endpoint
        primary_url = (
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(request.query)}"
        )
        try:
            transport = httpx.AsyncHTTPTransport(retries=1, verify=False)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.get(primary_url, headers=headers)
                if res.status_code == 200 and res.text:
                    candidates = self._parse_ddg_html(res.text, request)
                    if candidates:
                        return candidates
        except Exception as exc:
            logger.debug(
                "Primary DDG HTML search failed for '%s': %s", request.query, exc
            )

        # 2. Resilient Fallback: DDG Lite Endpoint (post/get table format)
        lite_url = "https://lite.duckduckgo.com/lite/"
        try:
            transport = httpx.AsyncHTTPTransport(retries=1, verify=False)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.post(
                    lite_url,
                    data={"q": request.query, "b": ""},
                    headers={
                        **headers,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                if res.status_code == 200 and res.text:
                    candidates = self._parse_ddg_lite(res.text, request)
                    if candidates:
                        return candidates
        except Exception as exc:
            logger.warning(
                "Fallback DDG Lite search failed for '%s': %s", request.query, exc
            )

        return []
