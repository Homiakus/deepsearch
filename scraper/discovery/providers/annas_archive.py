"""Anna's Archive Open Literature Discovery Provider (DS-SI08)."""

import logging
import urllib.parse
import httpx
from typing import List
from selectolax.parser import HTMLParser
from scraper.config import settings
from scraper.discovery.providers.base import ProviderDescriptor, ProviderSearchRequest
from scraper.search.candidates import SourceCandidate

logger = logging.getLogger(__name__)


class AnnasArchiveProvider:
    descriptor = ProviderDescriptor(
        name="annas_archive",
        supported_domains=["annas-archive.cc", "annas-archive.org", "annas-archive.li"],
        supported_source_types=["PRIMARY_RESEARCH", "OFFICIAL_DOC"],
        languages=["en", "ru"],
        freshness_capability="ARCHIVAL",
        cost_class="FREE",
    )

    async def search(self, request: ProviderSearchRequest) -> List[SourceCandidate]:
        base_url = getattr(
            settings, "annas_archive_url", "https://annas-archive.cc"
        ).rstrip("/")
        encoded = urllib.parse.quote(request.query)
        candidates = []
        seen_urls = set()
        headers = {
            "User-Agent": getattr(
                settings.robots,
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            )
        }

        endpoints = [
            f"{base_url}/s/?q={encoded}",
            f"{base_url}/articles?q={encoded}",
        ]

        try:
            transport = httpx.AsyncHTTPTransport(retries=2)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=request.timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                for ep in endpoints:
                    res = await client.get(ep, headers=headers, follow_redirects=True)
                    if res.status_code == 200 and res.text:
                        parser = HTMLParser(res.text)
                        for a in parser.css("a"):
                            href = a.attributes.get("href") or ""
                            if any(
                                k in href
                                for k in ["/book/", "/article/", "/md5/", "/db/"]
                            ):
                                full_url = (
                                    href
                                    if href.startswith("http")
                                    else f"{base_url}{href}"
                                )
                                if full_url not in seen_urls:
                                    seen_urls.add(full_url)
                                    text_title = a.text(strip=True) or request.query
                                    candidates.append(
                                        SourceCandidate(
                                            url=full_url,
                                            canonical_url=full_url,
                                            title=text_title[:150],
                                            snippet="Open library / paper document candidate",
                                            provider=self.descriptor.name,
                                            provider_rank=len(candidates) + 1,
                                            source_type="PRIMARY_RESEARCH",
                                            goal_ids=[request.goal_id]
                                            if request.goal_id
                                            else [],
                                            authority_prior=0.85,
                                        )
                                    )
                                    if len(candidates) >= request.max_results:
                                        break
                    if len(candidates) >= request.max_results:
                        break
        except Exception as exc:
            logger.warning(
                "AnnasArchiveProvider search error for query '%s': %s",
                request.query,
                exc,
            )

        return candidates
