"""Adaptive Acquisition Engine (§6, DS-RB37)."""

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
    """Orchestrates capability-oriented adaptive page acquisition (§2, §6, DS-RB37)."""

    def __init__(
        self,
        http_fetcher: Optional[FetcherProtocol] = None,
        browser_pool: Optional[BrowserPoolProtocol] = None,
        acquisition_backend: Optional[AcquisitionBackend] = None,
    ):
        self.http_fetcher: FetcherProtocol = http_fetcher or HTTPFetcher()
        self.browser_pool: BrowserPoolProtocol = browser_pool or BrowserPoolManager()
        self.acquisition_backend: Optional[AcquisitionBackend] = acquisition_backend

    async def acquire_page(
        self,
        url: str,
        canonical_url: str,
        mode: ExecutionMode = ExecutionMode.BALANCED,
        cached_content: Optional[bytes] = None,
        take_screenshot: bool = False
    ) -> CapturedArtifact:
        start_t = time.time()

        # L0: Cache (§6.1 L0)
        if cached_content:
            text = cached_content.decode("utf-8", errors="ignore")
            pi = classify_page(url, 200, {"content-type": "text/html"}, text)
            return CapturedArtifact(
                url=url,
                canonical_url=canonical_url,
                strategy_used=StrategyEscalation.CACHE,
                status_code=200,
                content_type="text/html",
                raw_content=cached_content,
                text_content=text,
                page_intelligence=pi,
                elapsed_sec=time.time() - start_t
            )

        # Capability-based Acquisition Backend path (if provided)
        if self.acquisition_backend:
            req_caps = BrowserCapabilities.minimal_http()
            if take_screenshot or mode in (ExecutionMode.RESEARCH, ExecutionMode.COMPLETE):
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

        # L1: Direct HTTP GET (§6.1 L1)
        http_res: Optional[HTTPResponse] = None
        try:
            http_res = await self.http_fetcher.fetch(url)
        except Exception as exc:
            logger.warning("L1 HTTP acquisition attempt failed for %s: %s", url, exc)

        if http_res and http_res.status_code == 200:
            pi = classify_page(
                url, http_res.status_code, http_res.headers, http_res.text
            )

            # Fast mode or static score high enough without blocks => return L1 HTTP
            if mode == ExecutionMode.FAST or (
                pi.js_dependency_score < settings.adaptive.browser_threshold and not take_screenshot and pi.block_score < 0.5
            ):
                return CapturedArtifact(
                    url=http_res.url,
                    canonical_url=canonical_url,
                    strategy_used=StrategyEscalation.HTTP,
                    status_code=http_res.status_code,
                    content_type=http_res.content_type,
                    raw_content=http_res.content,
                    text_content=http_res.text,
                    page_intelligence=pi,
                    elapsed_sec=http_res.elapsed_sec
                )

            # L2: Direct API Discovery Check (§6.1 L2, §30)
            if pi.api_score >= 0.7 and pi.detected_apis and settings.adaptive.api_preference:
                try:
                    api_res = await self.http_fetcher.fetch(pi.detected_apis[0])
                    if api_res.status_code == 200:
                        return CapturedArtifact(
                            url=api_res.url,
                            canonical_url=canonical_url,
                            strategy_used=StrategyEscalation.API,
                            status_code=api_res.status_code,
                            content_type=api_res.content_type,
                            raw_content=api_res.content,
                            text_content=api_res.text,
                            page_intelligence=pi,
                            elapsed_sec=api_res.elapsed_sec
                        )
                except Exception as api_exc:
                    logger.debug("L2 API probe failed for endpoint %s: %s", pi.detected_apis[0], api_exc)

        # L3: Browser Escalation (Playwright Chromium) (§6.1 L3)
        try:
            browser_res: BrowserResponse = await self.browser_pool.fetch_page(
                url,
                visual_mode=take_screenshot or (mode in (ExecutionMode.RESEARCH, ExecutionMode.COMPLETE)),
                take_screenshot=take_screenshot
            )
            pi = classify_page(
                browser_res.url,
                browser_res.status_code,
                browser_res.headers,
                browser_res.content,
                browser_res.network_requests
            )
            strategy = StrategyEscalation.VISUAL if browser_res.screenshot_bytes else StrategyEscalation.BROWSER

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
                elapsed_sec=time.time() - start_t
            )
        except Exception as e:
            # Fallback to HTTP if browser fails
            if http_res:
                logger.warning("L3 Browser failed for %s, falling back to L1 HTTP result: %s", url, e)
                pi = classify_page(url, http_res.status_code, http_res.headers, http_res.text)
                return CapturedArtifact(
                    url=http_res.url,
                    canonical_url=canonical_url,
                    strategy_used=StrategyEscalation.HTTP,
                    status_code=http_res.status_code,
                    content_type=http_res.content_type,
                    raw_content=http_res.content,
                    text_content=http_res.text,
                    page_intelligence=pi,
                    elapsed_sec=http_res.elapsed_sec
                )
            raise AcquisitionError(f"Failed to acquire page {url}: {e}") from e
