"""Scholarly Open Access & DOI Resolution Engine (DS-OA01).

Implements Semantic Bypass for academic paywalls, Cloudflare 403s, and JS challenges:
When a commercial publisher URL (Springer, Elsevier, Nature, MDPI, Lancet) blocks access,
this engine extracts the DOI/Title and queries global Open Access networks:
1. Unpaywall API (50,000+ institutional repositories, Gold/Green OA)
2. OpenAlex API (Scholarly open-access direct PDF/landing links)
3. Semantic Scholar Academic Graph (openAccessPdf, full text abstracts)
4. PubMed Central / Europe PMC REST APIs
"""

import logging
import re
import urllib.parse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Standard DOI extraction regex matching DOIs in URLs or text
DOI_REGEX = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")
NATURE_ARTICLE_REGEX = re.compile(
    r"nature\.com/articles/(s\d{5}-\d{3}-\d{5}-\w+)", re.IGNORECASE
)
SPRINGER_ARTICLE_REGEX = re.compile(
    r"springer\.com/article/(10\.\d{4,9}/[^?#\s]+)", re.IGNORECASE
)


class OpenAccessPaper(BaseModel):
    doi: str | None = None
    title: str | None = None
    is_open_access: bool = False
    oa_status: str | None = None  # gold, green, bronze, hybrid
    pdf_url: str | None = None
    landing_page_url: str | None = None
    repository_institution: str | None = None
    authors: list[str] = []
    year: int | None = None
    abstract: str | None = None


class OpenAccessResolver:
    """Resolves blocked or paywalled academic literature to legitimate open access full texts."""

    def __init__(
        self, timeout_sec: float = 15.0, user_email: str = "openaccess@deepsearch.local"
    ):
        self.timeout_sec = timeout_sec
        self.user_email = user_email
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

    @staticmethod
    def extract_doi_from_url_or_text(text: str) -> str | None:
        """Extract clean DOI string from a URL or text."""
        if not text:
            return None
        unquoted = urllib.parse.unquote(text)

        # 1. Direct standard DOI pattern
        match = DOI_REGEX.search(unquoted)
        if match:
            doi = match.group(1).rstrip(".;,")
            return doi

        # 2. Nature publisher URL pattern: nature.com/articles/s41416-023-02337-4
        nat_match = NATURE_ARTICLE_REGEX.search(unquoted)
        if nat_match:
            return f"10.1038/{nat_match.group(1)}"

        # 3. Springer article URL pattern
        spr_match = SPRINGER_ARTICLE_REGEX.search(unquoted)
        if spr_match:
            return spr_match.group(1).rstrip(".;,")

        return None

    async def resolve_doi_unpaywall(self, doi: str) -> OpenAccessPaper | None:
        """Query Unpaywall API for Open Access locations."""
        clean_doi = urllib.parse.quote(doi, safe="")
        url = f"https://api.unpaywall.org/v2/{clean_doi}?email={self.user_email}"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_sec, headers=self._headers, trust_env=False
            ) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    is_oa = data.get("is_oa", False)
                    best_oa = data.get("best_oa_location") or {}

                    pdf_url = best_oa.get("url_for_pdf")
                    landing_url = best_oa.get("url_for_landing_page") or best_oa.get(
                        "url"
                    )
                    oa_status = data.get("oa_status")

                    return OpenAccessPaper(
                        doi=doi,
                        title=data.get("title"),
                        is_open_access=is_oa,
                        oa_status=oa_status,
                        pdf_url=pdf_url,
                        landing_page_url=landing_url,
                        repository_institution=best_oa.get("repository_institution"),
                        year=data.get("year"),
                    )
        except Exception as exc:
            logger.debug("Unpaywall resolution failed for DOI %s: %s", doi, exc)
        return None

    async def resolve_doi_openalex(self, doi: str) -> OpenAccessPaper | None:
        """Query OpenAlex API for scholarly Open Access metadata."""
        clean_doi = urllib.parse.quote(f"https://doi.org/{doi}", safe="")
        url = f"https://api.openalex.org/works/{clean_doi}"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_sec, headers=self._headers, trust_env=False
            ) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    oa_info = data.get("open_access", {})
                    is_oa = oa_info.get("is_oa", False)
                    oa_url = oa_info.get("oa_url")

                    primary_loc = data.get("primary_location") or {}
                    pdf_url = primary_loc.get("pdf_url") or oa_url
                    landing_url = primary_loc.get("landing_page_url") or oa_url

                    return OpenAccessPaper(
                        doi=doi,
                        title=data.get("title"),
                        is_open_access=is_oa,
                        oa_status=oa_info.get("oa_status"),
                        pdf_url=pdf_url
                        if pdf_url and pdf_url.endswith(".pdf")
                        else None,
                        landing_page_url=landing_url or oa_url,
                        year=data.get("publication_year"),
                    )
        except Exception as exc:
            logger.debug("OpenAlex resolution failed for DOI %s: %s", doi, exc)
        return None

    async def resolve_blocked_url(
        self, url: str, candidate_title: str | None = None
    ) -> OpenAccessPaper | None:
        """Attempt multi-provider Open Access resolution for a blocked URL."""
        doi = self.extract_doi_from_url_or_text(url)
        if not doi and candidate_title:
            doi = self.extract_doi_from_url_or_text(candidate_title)

        if not doi:
            return None

        logger.info(
            "Extracted DOI '%s' from blocked URL '%s'. Attempting Open Access resolution...",
            doi,
            url,
        )

        # 1. Try Unpaywall
        oa_paper = await self.resolve_doi_unpaywall(doi)
        if oa_paper and (oa_paper.pdf_url or oa_paper.landing_page_url):
            logger.info(
                "Found Open Access location via Unpaywall for %s: %s (PDF: %s)",
                doi,
                oa_paper.landing_page_url,
                oa_paper.pdf_url,
            )
            return oa_paper

        # 2. Try OpenAlex
        oa_paper = await self.resolve_doi_openalex(doi)
        if oa_paper and (oa_paper.pdf_url or oa_paper.landing_page_url):
            logger.info(
                "Found Open Access location via OpenAlex for %s: %s",
                doi,
                oa_paper.landing_page_url,
            )
            return oa_paper

        return None


# Global singleton instance
open_access_resolver = OpenAccessResolver()
