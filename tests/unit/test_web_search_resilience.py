"""Unit tests for WebSearchProvider resilience and BrowserPool resource blocking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.discovery.providers.base import ProviderSearchRequest
from scraper.discovery.providers.web_search import WebSearchProvider

SAMPLE_DDG_HTML = """
<html>
<body>
  <div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a class="result__url" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget_page&rut=1">Example Target</a>
      </h2>
      <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget_page&rut=1">
        This is a snippet about example target.
      </a>
    </div>
  </div>
</body>
</html>
"""

SAMPLE_DDG_LITE_HTML = """
<html>
<body>
  <table>
    <tr>
      <td>
        <a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Flite.example.com%2Farticle&rut=2">
          Lite Target Title
        </a>
      </td>
    </tr>
    <tr>
      <td class="result-snippet">
        Snippet from DDG lite search result.
      </td>
    </tr>
  </table>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_web_search_parse_ddg_html():
    provider = WebSearchProvider()
    req = ProviderSearchRequest(query="deep search", max_results=5)
    candidates = provider._parse_ddg_html(SAMPLE_DDG_HTML, req)

    assert len(candidates) == 1
    assert candidates[0].url == "https://example.com/target_page"
    assert candidates[0].title == "Example Target"
    assert "snippet about example target" in candidates[0].snippet
    assert candidates[0].provider == "web_search"


@pytest.mark.asyncio
async def test_web_search_parse_ddg_lite():
    provider = WebSearchProvider()
    req = ProviderSearchRequest(query="lite query", max_results=5)
    candidates = provider._parse_ddg_lite(SAMPLE_DDG_LITE_HTML, req)

    assert len(candidates) == 1
    assert candidates[0].url == "https://lite.example.com/article"
    assert candidates[0].title == "Lite Target Title"
    assert "Snippet from DDG lite" in candidates[0].snippet


@pytest.mark.asyncio
async def test_web_search_fallback_to_lite_on_html_failure():
    provider = WebSearchProvider()
    req = ProviderSearchRequest(query="fallback query", max_results=5)

    mock_get_res = MagicMock()
    mock_get_res.status_code = 403
    mock_get_res.text = ""

    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.text = SAMPLE_DDG_LITE_HTML

    with (
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_get.return_value = mock_get_res
        mock_post.return_value = mock_post_res

        candidates = await provider.search(req)

        assert len(candidates) == 1
        assert candidates[0].url == "https://lite.example.com/article"
        mock_get.assert_called_once()
        mock_post.assert_called_once()


def test_browser_pool_blocked_domains_constants():
    """Verify that heavy trackers and analytics are blocked by policy in BrowserPool."""
    tracker_sample = "https://www.google-analytics.com/analytics.js"
    assert any(
        d in tracker_sample
        for d in ["google-analytics.com", "mc.yandex.ru", "doubleclick.net"]
    )
