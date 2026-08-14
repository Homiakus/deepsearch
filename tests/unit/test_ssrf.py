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
