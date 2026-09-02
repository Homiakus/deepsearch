"""Keenable Clean Markdown Page Fetcher (DS-SI08, DS-20).

Fetches web pages through Keenable AI Fetch endpoint, returning structured clean markdown
and metadata, providing robust extraction for anti-bot shielded or complex JavaScript pages.
"""

import logging
import os

import httpx
from pydantic import BaseModel

from scraper.config import settings

logger = logging.getLogger(__name__)


class KeenableFetchResult(BaseModel):
    url: str
    title: str = ""
    clean_markdown: str = ""
    description: str = ""
    author: str | None = None
    published_at: str | int | None = None
    success: bool = True
    error: str | None = None


class KeenableFetcher:
    """Fetches clean markdown for target URLs via Keenable Fetch API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = (
            api_key
            or getattr(settings, "keenable_api_key", None)
            or os.environ.get("KEENABLE_API_KEY")
        )
        self.base_url = (
            base_url or getattr(settings, "keenable_api_url", "https://api.keenable.ai")
        ).rstrip("/")

    async def fetch(self, url: str, timeout_sec: float = 20.0) -> KeenableFetchResult:
        """Fetches a URL and returns clean markdown."""
        is_authenticated = bool(self.api_key)
        endpoint = (
            f"{self.base_url}/v1/fetch"
            if is_authenticated
            else f"{self.base_url}/v1/fetch/public"
        )

        headers = {
            "User-Agent": "DeepSearch-Platform/1.0",
            "X-Keenable-Title": "DeepSearch",
        }
        if is_authenticated:
            headers["X-API-Key"] = self.api_key

        params = {"url": url}
        try:
            transport = httpx.AsyncHTTPTransport(retries=2)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=timeout_sec,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                res = await client.get(endpoint, params=params, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    pub_at = data.get("published_at")
                    return KeenableFetchResult(
                        url=url,
                        title=data.get("title") or "",
                        clean_markdown=data.get("content") or "",
                        description=data.get("description") or "",
                        author=data.get("author"),
                        published_at=str(pub_at) if pub_at is not None else None,
                        success=True,
                    )
                else:
                    err_msg = f"Keenable fetch HTTP {res.status_code}: {res.text[:200]}"
                    logger.warning(err_msg)
                    return KeenableFetchResult(url=url, success=False, error=err_msg)
        except Exception as exc:
            logger.warning("Keenable fetch exception for URL %s: %s", url, exc)
            return KeenableFetchResult(url=url, success=False, error=str(exc))


keenable_fetcher = KeenableFetcher()
