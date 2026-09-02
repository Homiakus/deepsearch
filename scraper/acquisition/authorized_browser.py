"""Authorized Playwright Browser & Interactive File Downloader (§9, §10, §75).

Provides persistent browser session management, user authentication storage,
anti-detection stealth parameters, and automated file download handling for protected portals
(e.g., Anna's Archive, Z-Library, Sci-Hub, IEEE, ScienceDirect).
"""

import logging
import os

from pydantic import BaseModel

from scraper.config import settings

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class DownloadResult(BaseModel):
    success: bool
    url: str
    saved_path: str | None = None
    filename: str | None = None
    file_size_bytes: int = 0
    error_message: str | None = None


class AuthorizedBrowserManager:
    """Manages persistent Playwright browser sessions and download events."""

    def __init__(self, user_data_dir: str | None = None):
        self.user_data_dir = os.path.abspath(
            user_data_dir
            or getattr(settings, "browser_user_data_dir", ".browser_profile")
        )
        os.makedirs(self.user_data_dir, exist_ok=True)

    async def launch_interactive_session(
        self, target_url: str = "https://annas-archive.cc", timeout_sec: int = 120
    ) -> str:
        """Launches a headed Chromium browser window for user login/captcha solving and saves state.json."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed in current virtualenv.")

        state_path = os.path.join(self.user_data_dir, "state.json")
        logger.info(
            f"Starting Interactive Authorized Browser session (user profile: {self.user_data_dir})..."
        )

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
            )

            page = context.pages[0] if context.pages else await context.new_page()

            # Enable stealth evasion
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            logger.info("Opening browser window at: %s", target_url)
            logger.info(
                "Complete any required log in, captcha, or file download in the browser window."
            )
            logger.info(
                "Closing window will automatically save your session cookies to: %s",
                state_path,
            )

            try:
                await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=60000
                )
            except Exception as e:
                logger.warning(f"Initial page navigation warning: {e}")

            # Keep session open until closed or timeout
            try:
                await page.wait_for_timeout(timeout_sec * 1000)
            except Exception:
                pass

            # Save state.json
            await context.storage_state(path=state_path)
            await context.close()
            logger.info(f"Browser session state saved successfully to {state_path}")
            return state_path

    async def download_file(
        self,
        url: str,
        output_dir: str = "laser_research_dataset/pdfs",
        click_selector: str | None = None,
        headless: bool = True,
    ) -> DownloadResult:
        """Downloads a file using persistent browser context and Playwright download handler."""
        if not PLAYWRIGHT_AVAILABLE:
            return DownloadResult(
                success=False, url=url, error_message="Playwright is not installed."
            )

        os.makedirs(output_dir, exist_ok=True)

        async with async_playwright() as p:
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                    viewport={"width": 1280, "height": 800},
                    accept_downloads=True,
                )

                page = context.pages[0] if context.pages else await context.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )

                logger.info(f"Navigating with Authorized Browser to {url}...")

                # Expect download event
                async with page.expect_download(timeout=45000) as download_info:
                    if click_selector:
                        await page.goto(
                            url, wait_until="domcontentloaded", timeout=30000
                        )
                        await page.click(click_selector, timeout=10000)
                    else:
                        await page.goto(url, timeout=30000)

                download = await download_info.value
                suggested_filename = download.suggested_filename
                save_path = os.path.join(output_dir, suggested_filename)

                await download.save_as(save_path)
                file_size = (
                    os.path.getsize(save_path) if os.path.exists(save_path) else 0
                )

                logger.info(
                    f"Successfully downloaded file: {suggested_filename} ({file_size} bytes)"
                )
                await context.close()

                return DownloadResult(
                    success=True,
                    url=url,
                    saved_path=save_path,
                    filename=suggested_filename,
                    file_size_bytes=file_size,
                )

            except Exception as e:
                logger.warning(f"Playwright download error for {url}: {e}")
                return DownloadResult(success=False, url=url, error_message=str(e))
