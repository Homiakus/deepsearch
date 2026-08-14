"""Playwright Browser Pool Manager (§9, §10, §75 Browser Isolation)."""

import asyncio
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from scraper.config import settings
from scraper.acquisition.http_fetcher import HTTPFetcher
from scraper.exceptions import BrowserPoolError

try:
    from playwright.async_api import async_playwright, Playwright, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserResponse(BaseModel):
    url: str
    status_code: int
    content: str
    screenshot_bytes: Optional[bytes] = None
    network_requests: List[Dict[str, Any]] = Field(default_factory=list)
    headers: Dict[str, str] = Field(default_factory=dict)


class BrowserPoolManager:
    """Manages persistent Chromium instances and isolated BrowserContexts (§9)."""

    def __init__(self, max_browsers: int = 2, contexts_per_browser: int = 10):
        self.max_browsers = max_browsers
        self.contexts_per_browser = contexts_per_browser
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Start Playwright engine and launch Chromium instance."""
        if not PLAYWRIGHT_AVAILABLE:
            return

        async with self._lock:
            if not self._playwright:
                try:
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                            "--disable-setuid-sandbox"
                        ]
                    )
                except Exception as e:
                    raise BrowserPoolError(f"Failed to initialize Playwright browser instance: {e}") from e

    async def fetch_page(
        self,
        url: str,
        visual_mode: bool = False,
        wait_for_selector: Optional[str] = None,
        take_screenshot: bool = False
    ) -> BrowserResponse:
        """Fetch URL using Playwright Chromium with resource blocking & SSRF validation (§10, §72)."""
        if not PLAYWRIGHT_AVAILABLE:
            raise BrowserPoolError("Playwright is not installed.")

        # SSRF pre-check before browser navigation
        HTTPFetcher.validate_url_security(url)

        await self.initialize()
        if not self._browser:
            raise BrowserPoolError("Browser pool is uninitialized.")

        # Create isolated BrowserContext (§9)
        context = await self._browser.new_context(
            user_agent=settings.robots.user_agent,
            viewport={"width": 1280, "height": 800} if visual_mode else {"width": 800, "height": 600}
        )

        page = await context.new_page()
        network_logs: List[Dict[str, Any]] = []

        # Intercept network requests (§29 Network Intelligence)
        def handle_response(res):
            network_logs.append({
                "url": res.url,
                "status": res.status,
                "mime": res.headers.get("content-type", ""),
                "size": 0
            })

        page.on("response", handle_response)

        # Resource blocking (§10): disable images, fonts, media unless visual_mode is true
        if not visual_mode:
            async def route_handler(route):
                req = route.request
                if req.resource_type in ["image", "media", "font", "stylesheet"]:
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", route_handler)

        try:
            res = await page.goto(url, wait_until="networkidle", timeout=30000)
            status_code = res.status if res else 200

            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=5000)
                except Exception:
                    pass

            content = await page.content()
            screenshot_bytes = None
            if take_screenshot or visual_mode:
                screenshot_bytes = await page.screenshot(full_page=True)

            return BrowserResponse(
                url=page.url,
                status_code=status_code,
                content=content,
                screenshot_bytes=screenshot_bytes,
                network_requests=network_logs,
                headers=dict(res.headers) if res else {}
            )
        finally:
            await context.close()

    async def close(self):
        """Shut down Playwright instance cleanly."""
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
