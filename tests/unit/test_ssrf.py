"""Unit tests for SSRF pre-flight protection."""

import pytest

from scraper.acquisition.http_fetcher import HTTPFetcher
from scraper.exceptions import SSRFError


def test_ssrf_blocked_localhost():
    """Verify that localhost URLs raise SSRFError."""
    with pytest.raises(SSRFError):
        HTTPFetcher.validate_url_security("http://127.0.0.1/admin")


def test_ssrf_blocked_private_ip():
    """Verify that private IP ranges (10.x, 192.168.x) raise SSRFError."""
    with pytest.raises(SSRFError):
        HTTPFetcher.validate_url_security("http://10.0.0.1/internal")

    with pytest.raises(SSRFError):
        HTTPFetcher.validate_url_security("http://192.168.1.1/router")


def test_ssrf_blocked_metadata_service():
    """Verify that AWS cloud metadata endpoint (169.254.169.254) raises SSRFError."""
    with pytest.raises(SSRFError):
        HTTPFetcher.validate_url_security("http://169.254.169.254/latest/meta-data/")


def test_ssrf_allowed_public_protocol():
    """Verify valid public protocols do not raise SSRFError for valid URLs."""
    # Should not raise for valid scheme
    HTTPFetcher.validate_url_security("https://example.com/page")


@pytest.mark.asyncio
async def test_redirect_target_revalidated():
    """FRAG-010: Redirect targets to private/loopback destinations must be revalidated and blocked before connection."""
    import httpx

    from scraper.exceptions import SSRFBlockedError
    from scraper.security.url_policy import url_security_policy

    with pytest.raises(SSRFBlockedError):
        url_security_policy.validate_url("http://127.0.0.1/admin")

    with pytest.raises(SSRFBlockedError):
        url_security_policy.validate_url("http://169.254.169.254/latest")

    with pytest.raises(SSRFBlockedError):
        url_security_policy.validate_url("http://10.0.0.1/internal")

    # Mock HTTP transport that redirects public URL to private loopback
    async def mock_handler(request: httpx.Request):
        if request.url == "https://public-site.com/bounce":
            return httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1:8080/internal-secrets"},
            )
        return httpx.Response(200, text="Secret internal data")

    fetcher = HTTPFetcher(transport=httpx.MockTransport(mock_handler))
    with pytest.raises(SSRFBlockedError, match="blocked private/loopback"):
        await fetcher.fetch("https://public-site.com/bounce")


@pytest.mark.asyncio
async def test_fetcher_oversized_stream_raises_clean_error(monkeypatch):
    """FRAG-DEPENDENCY: Stream exceeding max_response_size_bytes is aborted without unbounded memory usage."""
    import httpx

    from scraper.config import settings

    monkeypatch.setattr(settings.security, "max_response_size_bytes", 1000)

    async def mock_handler(request: httpx.Request):
        # Return a stream larger than max_response_size_bytes
        large_chunk = b"X" * 500
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=large_chunk * 5,  # 2500 bytes > 1000 bytes
        )

    fetcher = HTTPFetcher(transport=httpx.MockTransport(mock_handler))
    with pytest.raises(ValueError, match="Response size exceeded max limit"):
        await fetcher.fetch("https://example.com/oversized")
