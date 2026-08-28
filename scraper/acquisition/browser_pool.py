"""Playwright Browser Pool Manager with Anti-Detection Stealth (§9, §10, §75 Browser Isolation)."""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from scraper.config import settings
from scraper.acquisition.http_fetcher import HTTPFetcher
from scraper.exceptions import BrowserPoolError
from scraper.security.url_policy import url_security_policy

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


# Anti-detection stealth script to override automation artifacts
STEALTH_EVASION_SCRIPT = """
(() => {
    // 1. Mask navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // 2. Mock realistic plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
        ],
    });

    // 3. Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'ru'],
    });

    // 4. Mock window.chrome
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            app: {},
            csi: () => {},
            loadTimes: () => {},
        };
    }

    // 5. Mock permissions
    if (navigator.permissions && navigator.permissions.query) {
        const origQuery = navigator.permissions.query;
        navigator.permissions.query = (params) => (
            params.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            origQuery(params)
        );
    }
})();
"""


class BrowserPoolManager:
    """Manages persistent Chromium instances and isolated BrowserContexts (§9) with stealth enhancements."""

    def __init__(self, max_browsers: int = 2, contexts_per_browser: int = 10):
        self.max_browsers = max_browsers
        self.contexts_per_browser = contexts_per_browser
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._storage_state_path = Path(".browser_profile/storage_state.json")
        self._init_failed: bool = False

    def is_available(self) -> bool:
        """Returns True if Playwright is installed and browser binary is accessible."""
        return PLAYWRIGHT_AVAILABLE and not self._init_failed

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Start Playwright engine and launch Chromium instance."""
        if not PLAYWRIGHT_AVAILABLE or self._init_failed:
            return

        async with self._lock:
            if not self._playwright:
                try:
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-infobars",
                            "--window-size=1920,1080",
                        ],
                    )
                except Exception as e:
                    self._init_failed = True
                    raise BrowserPoolError(
                        f"Failed to initialize Playwright browser instance: {e}"
                    ) from e

    async def fetch_page(
        self,
        url: str,
        visual_mode: bool = False,
        wait_for_selector: Optional[str] = None,
        take_screenshot: bool = False,
    ) -> BrowserResponse:
        """Fetch URL using Playwright Chromium with stealth anti-detection, resource management & SSRF validation."""
        if not PLAYWRIGHT_AVAILABLE:
            raise BrowserPoolError("Playwright is not installed.")

        # SSRF pre-check before browser navigation
        HTTPFetcher.validate_url_security(url)

        await self.initialize()
        if not self._browser:
            raise BrowserPoolError("Browser pool is uninitialized.")

        # Context options with realistic browser signature
        storage_state = (
            str(self._storage_state_path) if self._storage_state_path.exists() else None
        )

        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "viewport": {"width": 1366, "height": 768}
            if visual_mode
            else {"width": 1280, "height": 800},
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                "Sec-CH-UA": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        }
        if storage_state:
            context_kwargs["storage_state"] = storage_state

        context = await self._browser.new_context(**context_kwargs)

        # Inject anti-detection stealth script before document scripts run
        await context.add_init_script(STEALTH_EVASION_SCRIPT)

        page = await context.new_page()
        network_logs: List[Dict[str, Any]] = []

        # Intercept network requests (§29 Network Intelligence)
        def handle_response(res):
            network_logs.append(
                {
                    "url": res.url,
                    "status": res.status,
                    "mime": res.headers.get("content-type", ""),
                    "size": 0,
                }
            )

        page.on("response", handle_response)

        # SSRF subresource guard (§DS-07) and resource blocking (§10)
        async def route_handler(route):
            req = route.request
            try:
                url_security_policy.validate_url(req.url)
            except Exception:
                await route.abort("blockedbyclient")
                return

            if not visual_mode and req.resource_type in ["media", "font"]:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", route_handler)

        try:
            res = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(
                    settings.adaptive.browser_navigation_timeout_seconds * 1000
                ),
            )
            status_code = res.status if res else 200

            if wait_for_selector:
                try:
                    await page.wait_for_selector(
                        wait_for_selector,
                        timeout=int(
                            settings.adaptive.browser_selector_timeout_seconds * 1000
                        ),
                    )
                except Exception:
                    pass

            # Optional brief settling wait for challenge resolution
            await page.wait_for_timeout(1200)

            content = await page.content()
            screenshot_bytes = None

            if take_screenshot or visual_mode:
                try:
                    screenshot_bytes = await page.screenshot(
                        type="png", full_page=False
                    )
                except Exception:
                    pass

            return BrowserResponse(
                url=page.url,
                status_code=status_code,
                content=content,
                screenshot_bytes=screenshot_bytes,
                network_requests=network_logs,
                headers=dict(res.headers) if res else {},
            )
        finally:
            await context.close()

    async def close(self):
        """Close browser instance and clean up Playwright resources."""
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
