"""Adaptive Acquisition Engine (§6, DS-RB37, §DS-09)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from scraper.config import settings, ExecutionMode
from scraper.exceptions import AcquisitionError
from scraper.contracts import FetcherProtocol, BrowserPoolProtocol, AcquisitionBackend
from scraper.acquisition.http_fetcher import HTTPFetcher, HTTPResponse
from scraper.acquisition.browser_pool import BrowserPoolManager, BrowserResponse
from scraper.acquisition.page_classifier import classify_page, PageIntelligence
from scraper.control.planner import StrategyEscalation
from scraper.acquisition.capabilities import BrowserCapabilities, CapabilityLevel
from scraper.acquisition.models import AcquisitionRequest, AcquisitionResult

logger = logging.getLogger(__name__)


class CapturedArtifact(BaseModel):
    url: str
    canonical_url: str
    strategy_used: str
    status_code: int
    content_type: str
    raw_content: bytes
    text_content: str
    screenshot_bytes: Optional[bytes] = None
    page_intelligence: PageIntelligence
    network_logs: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_sec: float = 0.0


class AdaptiveAcquisitionEngine:
    """Orchestrates capability-oriented adaptive page acquisition with honest tiers (§DS-09)."""

    def __init__(
        self,
        http_fetcher: Optional[FetcherProtocol] = None,
        browser_pool: Optional[BrowserPoolProtocol] = None,
        acquisition_backend: Optional[AcquisitionBackend] = None,
    ):
        self.http_fetcher: FetcherProtocol = http_fetcher or HTTPFetcher()
        self.browser_pool: BrowserPoolProtocol = browser_pool or BrowserPoolManager()
        self.acquisition_backend: Optional[AcquisitionBackend] = acquisition_backend

    def should_escalate_to_browser(
        self,
        mode: ExecutionMode,
        pi: Optional[PageIntelligence],
        take_screenshot: bool,
        http_failed: bool,
    ) -> bool:
        """Table-driven decision function for browser escalation (McCabe <= 6)."""
        if mode == ExecutionMode.FAST:
            return False

        if take_screenshot or mode in (ExecutionMode.RESEARCH, ExecutionMode.COMPLETE):
            return True

        if http_failed:
            return True

        if pi is not None:
            if pi.js_dependency_score >= settings.adaptive.browser_threshold:
                return True
            if pi.block_score >= 0.5:
                return True

        return False

    async def acquire_page(
        self,
        url: str,
        canonical_url: str,
        mode: ExecutionMode = ExecutionMode.BALANCED,
        take_screenshot: bool = False,
    ) -> CapturedArtifact:
        """Acquire web page content via honest HTTP / Browser escalation tiers (§DS-09)."""
        start_t = time.time()

        # Capability-based Acquisition Backend path (if injected)
        if self.acquisition_backend:
            return await self._acquire_via_backend(
                url, canonical_url, mode, take_screenshot, start_t
            )

        # 1. Primary HTTP Acquisition Tier
        http_res: Optional[HTTPResponse] = None
        http_pi: Optional[PageIntelligence] = None
        http_failed = False

        try:
            http_res = await self.http_fetcher.fetch(url)
            if http_res.status_code == 200:
                http_pi = classify_page(
                    url, http_res.status_code, http_res.headers, http_res.text
                )
            else:
                http_failed = True
        except Exception as exc:
            logger.warning("HTTP acquisition attempt failed for %s: %s", url, exc)
            http_failed = True

        # Check if browser escalation is required according to strategy matrix
        needs_browser = self.should_escalate_to_browser(
            mode, http_pi, take_screenshot, http_failed
        )

        if not needs_browser and http_res and http_res.status_code == 200 and http_pi:
            return CapturedArtifact(
                url=http_res.url,
                canonical_url=canonical_url,
                strategy_used=StrategyEscalation.HTTP,
                status_code=http_res.status_code,
                content_type=http_res.content_type,
                raw_content=http_res.content,
                text_content=http_res.text,
                page_intelligence=http_pi,
                elapsed_sec=http_res.elapsed_sec,
            )

        # 2. Browser Escalation Tier (Playwright Chromium)
        browser_available = getattr(self.browser_pool, "is_available", lambda: True)()
        if not browser_available or mode == ExecutionMode.FAST:
            if http_res:
                pi = http_pi or classify_page(
                    url, http_res.status_code, http_res.headers, http_res.text
                )
                return CapturedArtifact(
                    url=http_res.url,
                    canonical_url=canonical_url,
                    strategy_used=StrategyEscalation.HTTP,
                    status_code=http_res.status_code,
                    content_type=http_res.content_type,
                    raw_content=http_res.content,
                    text_content=http_res.text,
                    page_intelligence=pi,
                    elapsed_sec=http_res.elapsed_sec,
                )
            raise AcquisitionError(
                f"Failed to acquire page {url}: browser unavailable and HTTP acquisition failed"
            )

        try:
            browser_res: BrowserResponse = await asyncio.wait_for(
                self.browser_pool.fetch_page(
                    url,
                    visual_mode=take_screenshot
                    or (mode in (ExecutionMode.RESEARCH, ExecutionMode.COMPLETE)),
                    take_screenshot=take_screenshot,
                ),
                timeout=float(
                    settings.adaptive.browser_navigation_timeout_seconds + 3.0
                ),
            )
            pi = classify_page(
                browser_res.url,
                browser_res.status_code,
                browser_res.headers,
                browser_res.content,
                browser_res.network_requests,
            )
            strategy = (
                StrategyEscalation.VISUAL
                if browser_res.screenshot_bytes
                else StrategyEscalation.BROWSER
            )

            return CapturedArtifact(
                url=browser_res.url,
                canonical_url=canonical_url,
                strategy_used=strategy,
                status_code=browser_res.status_code,
                content_type="text/html",
                raw_content=browser_res.content.encode("utf-8"),
                text_content=browser_res.content,
                screenshot_bytes=browser_res.screenshot_bytes,
                page_intelligence=pi,
                network_logs=browser_res.network_requests,
                elapsed_sec=time.time() - start_t,
            )
        except Exception as e:
            # Fallback to HTTP result if available
            if http_res:
                logger.warning(
                    "Browser tier failed for %s, falling back to HTTP result: %s",
                    url,
                    e,
                )
                pi = http_pi or classify_page(
                    url, http_res.status_code, http_res.headers, http_res.text
                )
                return CapturedArtifact(
                    url=http_res.url,
                    canonical_url=canonical_url,
                    strategy_used=StrategyEscalation.HTTP,
                    status_code=http_res.status_code,
                    content_type=http_res.content_type,
                    raw_content=http_res.content,
                    text_content=http_res.text,
                    page_intelligence=pi,
                    elapsed_sec=http_res.elapsed_sec,
                )
            raise AcquisitionError(f"Failed to acquire page {url}: {e}") from e

    async def _acquire_via_backend(
        self,
        url: str,
        canonical_url: str,
        mode: ExecutionMode,
        take_screenshot: bool,
        start_t: float,
    ) -> CapturedArtifact:
        """Helper to acquire via capability-oriented AcquisitionBackend."""
        assert self.acquisition_backend is not None
        req_caps = BrowserCapabilities.minimal_http()
        if take_screenshot or mode in (
            ExecutionMode.RESEARCH,
            ExecutionMode.COMPLETE,
        ):
            req_caps.screenshot = CapabilityLevel.SUPPORTED
            req_caps.javascript = CapabilityLevel.SUPPORTED

        req = AcquisitionRequest(
            url=url,
            canonical_url=canonical_url,
            required_capabilities=req_caps,
            mode=str(mode.value) if hasattr(mode, "value") else str(mode),
        )
        res: AcquisitionResult = await self.acquisition_backend.acquire(req)
        raw = res.raw_content or res.text_preview.encode("utf-8", errors="ignore")
        text = res.text_preview or raw.decode("utf-8", errors="ignore")
        pi = classify_page(res.final_url, res.status_code, res.headers, text)

        return CapturedArtifact(
            url=res.final_url,
            canonical_url=canonical_url,
            strategy_used=res.backend,
            status_code=res.status_code,
            content_type=res.content_type,
            raw_content=raw,
            text_content=text,
            screenshot_bytes=res.screenshot_bytes,
            page_intelligence=pi,
            network_logs=[],
            elapsed_sec=res.elapsed_sec or (time.time() - start_t),
        )
