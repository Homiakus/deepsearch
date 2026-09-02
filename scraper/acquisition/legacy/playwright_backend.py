"""Playwright Reference Backend Adapter (§9, DS-RB08, DS-RB09).

Wraps Playwright Chromium as a standardized AcquisitionBackend implementation
with bounded concurrency, isolated contexts, SSRF enforcement, and health monitoring.
"""

import asyncio
import importlib.util
import time

from scraper.acquisition.browser_pool import BrowserPoolManager, BrowserResponse
from scraper.acquisition.capabilities import (
    BackendDescriptor,
    BrowserCapabilities,
    CapabilityLevel,
)
from scraper.acquisition.models import (
    AcquisitionRequest,
    AcquisitionResult,
    CostReport,
    FailureRecord,
)
from scraper.acquisition.quality import AcquisitionQualityEvaluator

PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


class PlaywrightBackend:
    """Standardized AcquisitionBackend adapter wrapping Playwright Chromium."""

    def __init__(self, max_browsers: int = 2, contexts_per_browser: int = 5):
        self.max_browsers = max_browsers
        self.contexts_per_browser = contexts_per_browser
        self.max_concurrency = max_browsers * contexts_per_browser
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._pool = BrowserPoolManager(
            max_browsers=max_browsers, contexts_per_browser=contexts_per_browser
        )
        self._quality_evaluator = AcquisitionQualityEvaluator()

        self._descriptor = BackendDescriptor(
            name="chromium-playwright",
            version="1.0.0",
            engine_family="chromium",
            capabilities=BrowserCapabilities.create_full_browser(),
            experimental=False,
            base_cost=10.0,
            startup_cost=2.0,
            memory_class="high",
            concurrency_class="low",
            security_profile="standard",
            max_concurrency=self.max_concurrency,
        )

    @property
    def descriptor(self) -> BackendDescriptor:
        return self._descriptor

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        start_t = time.time()
        take_screenshot = (
            request.required_capabilities.screenshot == CapabilityLevel.SUPPORTED
            or request.mode in ("research", "complete")
        )

        async with self._semaphore:
            try:
                res: BrowserResponse = await self._pool.fetch_page(
                    url=request.url,
                    visual_mode=take_screenshot,
                    wait_for_selector=request.wait_condition,
                    take_screenshot=take_screenshot,
                )
                elapsed = time.time() - start_t

                quality = self._quality_evaluator.evaluate(
                    url=res.url,
                    status_code=res.status_code,
                    headers=res.headers,
                    html_or_text=res.content,
                )

                cost = CostReport(
                    base_cost=self._descriptor.base_cost,
                    execution_time_ms=elapsed * 1000.0,
                    memory_mb=120.0,
                    network_bytes=len(res.content.encode("utf-8")),
                )

                return AcquisitionResult(
                    requested_url=request.url,
                    final_url=res.url,
                    backend=self._descriptor.name,
                    backend_version=self._descriptor.version,
                    status_code=res.status_code,
                    headers=res.headers,
                    content_type="text/html",
                    raw_content=res.content.encode("utf-8"),
                    text_preview=res.content[:500],
                    screenshot_bytes=res.screenshot_bytes,
                    network_summary={"requests": len(res.network_requests)},
                    quality=quality,
                    cost=cost,
                    elapsed_sec=elapsed,
                    capabilities_used=["html", "javascript", "dom_mutation"]
                    + (["screenshot"] if res.screenshot_bytes else []),
                )

            except Exception as exc:
                elapsed = time.time() - start_t
                failure = FailureRecord(
                    failure_class="transient"
                    if "timeout" in str(exc).lower()
                    else "permanent",
                    message=str(exc),
                    retryable="timeout" in str(exc).lower(),
                )
                return AcquisitionResult(
                    requested_url=request.url,
                    final_url=request.url,
                    backend=self._descriptor.name,
                    backend_version=self._descriptor.version,
                    status_code=500,
                    failure=failure,
                    elapsed_sec=elapsed,
                )

    async def close(self):
        await self._pool.close()
