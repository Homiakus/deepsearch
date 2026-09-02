"""Unit tests for Crawlee adapter and robots policy (DS-A13, DS-A15)."""

import pytest

from scraper.acquisition.crawlee_adapter import CrawleeBatchCrawler
from scraper.discovery.robots import RobotsDecision, RobotsPolicyManager


def test_robots_policy_evaluation():
    mgr = RobotsPolicyManager(respect=True)
    robots_txt = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /public/
"""
    mgr.parse_robots_txt("example.com", robots_txt)

    allowed, decision = mgr.evaluate("https://example.com/public/page", "example.com")
    assert allowed is True
    assert decision == RobotsDecision.ALLOWED

    blocked, dec_blocked = mgr.evaluate(
        "https://example.com/private/secret", "example.com"
    )
    assert blocked is False
    assert dec_blocked == RobotsDecision.BLOCKED


@pytest.mark.asyncio
async def test_crawlee_batch_crawler_init():
    crawler = CrawleeBatchCrawler(max_concurrency=4)
    assert crawler.max_concurrency == 4
