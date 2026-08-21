"""Unit tests for Link Discovery (§19) and Robots.txt Policy Engine (§22)."""

import pytest
from scraper.discovery.links import (
    extract_links_from_html,
    extract_sitemap_urls,
    extract_canonical_link,
)
from scraper.discovery.robots import RobotsPolicyManager


def test_extract_links():
    html = """
    <html>
      <body>
        <a href="/docs/page1">Page 1</a>
        <a href="https://other.com/page2">Page 2</a>
        <a href="javascript:void(0)">Ignore</a>
      </body>
    </html>
    """
    links = extract_links_from_html(html, base_url="https://example.com/base")
    assert "https://example.com/docs/page1" in links
    assert "https://other.com/page2" in links
    assert len(links) == 2


def test_extract_sitemap_urls():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/page1</loc></url>
      <url><loc>https://example.com/page2</loc></url>
    </urlset>
    """
    urls = extract_sitemap_urls(xml)
    assert urls == ["https://example.com/page1", "https://example.com/page2"]


def test_extract_canonical_link():
    html = '<html><head><link rel="canonical" href="https://example.com/canonical-page"></head></html>'
    canonical = extract_canonical_link(html)
    assert canonical == "https://example.com/canonical-page"


def test_robots_policy():
    manager = RobotsPolicyManager()
    robots_txt = """
    User-agent: *
    Disallow: /private/
    Allow: /public/
    """
    manager.parse_robots_txt("example.com", robots_txt)
    assert manager.is_allowed("https://example.com/public/item", "example.com") is True
    assert (
        manager.is_allowed("https://example.com/private/secret", "example.com") is False
    )


@pytest.mark.asyncio
async def test_fetch_annas_archive_seeds():
    from unittest.mock import AsyncMock, patch
    from scraper.discovery.seed_finder import fetch_annas_archive_seeds

    sample_html = """
    <html>
        <body>
            <a href="/book/123456">Quantum Mechanics Book</a>
            <a href="/md5/abc123def456">Paper MD5</a>
            <a href="/article/7890">Research Article</a>
            <a href="/other/page">Ignored Link</a>
        </body>
    </html>
    """
    mock_res = AsyncMock()
    mock_res.status_code = 200
    mock_res.text = sample_html

    with patch("httpx.AsyncClient.get", return_value=mock_res):
        seeds = await fetch_annas_archive_seeds("quantum mechanics", max_results=5)
        assert len(seeds) == 3
        assert "https://annas-archive.cc/book/123456" in seeds
        assert "https://annas-archive.cc/md5/abc123def456" in seeds
        assert "https://annas-archive.cc/article/7890" in seeds


def test_provider_yield_tracker():
    from scraper.discovery.provider_policy import ProviderYieldTracker

    tracker = ProviderYieldTracker()
    assert tracker.get_health_factor("pubmed") == 1.0

    # Record healthy calls
    tracker.record_call("pubmed", candidate_count=10, error=False)
    assert tracker.get_health_factor("pubmed") == 1.0

    # Record failing calls
    tracker.record_call("flaky_prov", candidate_count=0, error=True)
    tracker.record_call("flaky_prov", candidate_count=0, error=True)
    tracker.record_call("flaky_prov", candidate_count=0, error=True)
    assert tracker.get_health_factor("flaky_prov") == 0.2

