"""Security tests for unified SSRF validation and URL policy (DS-A20, DS-A42, §DS-07)."""

from unittest.mock import patch

import pytest

from scraper.acquisition.media_downloader import download_media_file
from scraper.exceptions import SSRFBlockedError
from scraper.security.url_policy import URLSecurityPolicy


def test_block_direct_private_ips():
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://127.0.0.1/admin")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://10.0.0.1/status")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://192.168.1.1:8080/metrics")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://172.16.5.1/api")


def test_block_cloud_metadata_and_link_local():
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://0.0.0.0:8080/secret")


def test_block_ipv6_loopback_and_unspecified():
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::1]/secret")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::]/root")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[fe80::1]/link-local")


def test_block_ipv4_mapped_ipv6():
    """Verify IPv4-mapped IPv6 addresses resolving to private/loopback are blocked (§DS-07)."""
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::ffff:127.0.0.1]/secret")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::ffff:169.254.169.254]/latest")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::ffff:10.0.0.5]/internal")


def test_unsupported_schemes():
    """Verify non-HTTP/HTTPS protocols are rejected (§DS-07)."""
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("file:///etc/passwd")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("ftp://ftp.example.com/file")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("gopher://gopher.example.com")


def test_userinfo_confusion():
    """Verify userinfo cannot bypass host validation (§DS-07)."""
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://admin:pass@127.0.0.1:8080/api")

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://user@169.254.169.254/meta")


def test_dns_rebinding_resolution_blocked():
    """Verify hostname resolving to private IP is blocked during DNS resolution (§DS-07)."""
    policy = URLSecurityPolicy(block_private_ips=True)

    with patch("socket.getaddrinfo", return_value=[(2, 1, 0, "", ("127.0.0.1", 80))]):
        with pytest.raises(SSRFBlockedError, match="resolved to blocked private IP"):
            policy.validate_url("http://rebound-domain.evil.com/admin")


def test_allow_public_urls():
    policy = URLSecurityPolicy(block_private_ips=True)
    assert (
        policy.validate_url("https://example.com/dataset")
        == "https://example.com/dataset"
    )
    assert (
        policy.validate_url("https://arxiv.org/abs/2103.00020")
        == "https://arxiv.org/abs/2103.00020"
    )


@pytest.mark.asyncio
async def test_media_downloader_blocks_private_url():
    """Verify media downloader rejects private IP download target (§DS-07)."""
    res = await download_media_file("http://127.0.0.1/doc.pdf", output_dir="./tmp_test")
    assert res is None
