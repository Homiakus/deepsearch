"""Robots.txt Parser and Crawling Policy Engine (§22)."""

import urllib.robotparser
from typing import Optional, List
from scraper.config import settings


class RobotsPolicyManager:
    """Manages per-domain robots.txt rules (§22)."""

    def __init__(self):
        self._parsers = {}

    def parse_robots_txt(self, domain: str, robots_content: str):
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots_content.splitlines())
        self._parsers[domain] = rp

    def is_allowed(self, url: str, domain: str, user_agent: Optional[str] = None) -> bool:
        if not settings.robots.respect:
            return True

        rp = self._parsers.get(domain)
        if not rp:
            return True  # If no robots.txt loaded, default allowed

        ua = user_agent or settings.robots.user_agent
        return rp.can_fetch(ua, url)

    def get_sitemaps(self, domain: str) -> List[str]:
        rp = self._parsers.get(domain)
        if rp and hasattr(rp, "site_maps") and rp.site_maps():
            return rp.site_maps()
        return []
