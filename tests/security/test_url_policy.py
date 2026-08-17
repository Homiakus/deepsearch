"""Security tests for SSRF validation and URL policy (DS-A20, DS-A42)."""

import pytest
from scraper.security.url_policy import URLSecurityPolicy
from scraper.exceptions import SSRFBlockedError


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


def test_block_ipv6_loopback():
    policy = URLSecurityPolicy(block_private_ips=True)

    with pytest.raises(SSRFBlockedError):
        policy.validate_url("http://[::1]/secret")


def test_allow_public_urls():
    policy = URLSecurityPolicy(block_private_ips=True)
    assert policy.validate_url("https://example.com/dataset") == "https://example.com/dataset"
    assert policy.validate_url("https://arxiv.org/abs/2103.00020") == "https://arxiv.org/abs/2103.00020"
