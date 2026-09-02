"""Robots.txt Parser and Crawling Policy Engine (§22, DS-A13)."""

import urllib.parse
import urllib.robotparser
from enum import Enum

from scraper.config import settings


class RobotsDecision(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    UNKNOWN_ERROR = "unknown_error"
    POLICY_OVERRIDE = "policy_override"


class RobotsPolicyManager:
    """Manages per-domain robots.txt rules and provenance decisions (§22, DS-A13)."""

    def __init__(self, respect: bool | None = None):
        self.respect = respect if respect is not None else settings.robots.respect
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def parse_robots_txt(self, domain: str, robots_content: str):
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots_content.splitlines())
        self._parsers[domain] = rp

    def evaluate(
        self, url: str, domain: str | None = None, user_agent: str | None = None
    ) -> tuple[bool, RobotsDecision]:
        """Evaluates whether URL is allowed, returning boolean flag and typed provenance decision."""
        if not self.respect:
            return True, RobotsDecision.POLICY_OVERRIDE

        if not domain:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc

        rp = self._parsers.get(domain)
        if not rp:
            return True, RobotsDecision.ALLOWED

        ua = user_agent or settings.robots.user_agent
        can_fetch = rp.can_fetch(ua, url)
        decision = RobotsDecision.ALLOWED if can_fetch else RobotsDecision.BLOCKED
        return can_fetch, decision

    def is_allowed(
        self, url: str, domain: str | None = None, user_agent: str | None = None
    ) -> bool:
        allowed, _ = self.evaluate(url, domain, user_agent)
        return allowed

    def get_sitemaps(self, domain: str) -> list[str]:
        rp = self._parsers.get(domain)
        if rp and hasattr(rp, "site_maps") and rp.site_maps():
            return rp.site_maps()
        return []


robots_manager = RobotsPolicyManager()
