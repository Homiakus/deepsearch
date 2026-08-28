"""Table-driven unit tests for AdaptiveAcquisitionEngine (§DS-09)."""

from unittest.mock import AsyncMock
import pytest
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.acquisition.http_fetcher import HTTPResponse
from scraper.acquisition.browser_pool import BrowserResponse
from scraper.config import ExecutionMode
from scraper.control.planner import StrategyEscalation
from scraper.exceptions import AcquisitionError


@pytest.fixture
def mock_http_static():
    mock = AsyncMock()
    mock.fetch.return_value = HTTPResponse(
        url="https://example.com/static",
        status_code=200,
        headers={"content-type": "text/html"},
        content=b"<html><body><h1>Static Title</h1><p>Content text</p></body></html>",
        text="<html><body><h1>Static Title</h1><p>Content text</p></body></html>",
        content_type="text/html",
        elapsed_sec=0.05,
    )
    return mock


@pytest.fixture
def mock_http_spa():
    mock = AsyncMock()
    # SPA shell requiring JS
    mock.fetch.return_value = HTTPResponse(
        url="https://example.com/spa",
        status_code=200,
        headers={"content-type": "text/html"},
        content=b'<html><body><div id="react-root"></div><script src="react-dom.production.min.js"></script></body></html>',
        text='<html><body><div id="react-root"></div><script src="react-dom.production.min.js"></script></body></html>',
        content_type="text/html",
        elapsed_sec=0.05,
    )
    return mock


@pytest.fixture
def mock_browser_pool():
    mock = AsyncMock()
    mock.is_available = lambda: True
    mock.fetch_page.return_value = BrowserResponse(
        url="https://example.com/spa",
        status_code=200,
        content="<html><body><div id='root'>Rendered SPA content</div></body></html>",
        screenshot_bytes=None,
        network_requests=[],
        headers={"content-type": "text/html"},
    )
    return mock


@pytest.mark.asyncio
async def test_fast_mode_never_escalates(mock_http_spa, mock_browser_pool):
    """Verify FAST mode sticks to HTTP even for SPA pages with high JS dependency (§DS-09)."""
    engine = AdaptiveAcquisitionEngine(
        http_fetcher=mock_http_spa, browser_pool=mock_browser_pool
    )
    artifact = await engine.acquire_page(
        "https://example.com/spa",
        "https://example.com/spa",
        mode=ExecutionMode.FAST,
    )
    assert artifact.strategy_used == StrategyEscalation.HTTP
    assert not mock_browser_pool.fetch_page.called


@pytest.mark.asyncio
async def test_balanced_mode_static_stays_http(mock_http_static, mock_browser_pool):
    """Verify BALANCED mode uses HTTP for clean static pages (§DS-09)."""
    engine = AdaptiveAcquisitionEngine(
        http_fetcher=mock_http_static, browser_pool=mock_browser_pool
    )
    artifact = await engine.acquire_page(
        "https://example.com/static",
        "https://example.com/static",
        mode=ExecutionMode.BALANCED,
    )
    assert artifact.strategy_used == StrategyEscalation.HTTP
    assert not mock_browser_pool.fetch_page.called


@pytest.mark.asyncio
async def test_balanced_mode_spa_escalates_to_browser(mock_http_spa, mock_browser_pool):
    """Verify BALANCED mode escalates to Browser for SPA/JS pages (§DS-09)."""
    engine = AdaptiveAcquisitionEngine(
        http_fetcher=mock_http_spa, browser_pool=mock_browser_pool
    )
    artifact = await engine.acquire_page(
        "https://example.com/spa",
        "https://example.com/spa",
        mode=ExecutionMode.BALANCED,
    )
    assert artifact.strategy_used == StrategyEscalation.BROWSER
    assert mock_browser_pool.fetch_page.called


@pytest.mark.asyncio
async def test_screenshot_requested_escalates_to_visual(
    mock_http_static, mock_browser_pool
):
    """Verify requesting screenshot triggers browser and returns VISUAL strategy (§DS-09)."""
    mock_browser_pool.fetch_page.return_value = BrowserResponse(
        url="https://example.com/static",
        status_code=200,
        content="<html><body>Rendered</body></html>",
        screenshot_bytes=b"\x89PNGfake",
        network_requests=[],
        headers={},
    )
    engine = AdaptiveAcquisitionEngine(
        http_fetcher=mock_http_static, browser_pool=mock_browser_pool
    )
    artifact = await engine.acquire_page(
        "https://example.com/static",
        "https://example.com/static",
        mode=ExecutionMode.BALANCED,
        take_screenshot=True,
    )
    assert artifact.strategy_used == StrategyEscalation.VISUAL
    assert artifact.screenshot_bytes == b"\x89PNGfake"


@pytest.mark.asyncio
async def test_browser_unavailable_falls_back_to_http(mock_http_spa):
    """Verify browser failure gracefully falls back to available HTTP content (§DS-09)."""
    unavailable_browser = AsyncMock()
    unavailable_browser.is_available = lambda: False

    engine = AdaptiveAcquisitionEngine(
        http_fetcher=mock_http_spa, browser_pool=unavailable_browser
    )
    artifact = await engine.acquire_page(
        "https://example.com/spa",
        "https://example.com/spa",
        mode=ExecutionMode.BALANCED,
    )
    assert artifact.strategy_used == StrategyEscalation.HTTP
    assert artifact.status_code == 200


@pytest.mark.asyncio
async def test_total_acquisition_failure_raises_error():
    """Verify when both HTTP and Browser fail, an explicit AcquisitionError is raised (§DS-09)."""
    failing_http = AsyncMock()
    failing_http.fetch.side_effect = ConnectionError("Network unreachable")

    failing_browser = AsyncMock()
    failing_browser.is_available.return_value = True
    failing_browser.fetch_page.side_effect = TimeoutError("Browser timeout")

    engine = AdaptiveAcquisitionEngine(
        http_fetcher=failing_http, browser_pool=failing_browser
    )
    with pytest.raises(AcquisitionError, match="Failed to acquire page"):
        await engine.acquire_page(
            "https://example.com/down",
            "https://example.com/down",
            mode=ExecutionMode.BALANCED,
        )
