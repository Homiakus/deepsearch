"""Unit tests for URL Canonicalization Engine (§16)."""

from scraper.normalization.canonicalizer import canonicalize_url


def test_canonicalize_url_basic():
    raw = "HTTP://Example.COM:80/docs/index.html?utm_source=google&b=2&a=1#section1"
    expected = "http://example.com/docs/index.html?a=1&b=2"
    assert canonicalize_url(raw) == expected


def test_canonicalize_tracking_removal():
    raw = "https://site.com/product?fbclid=12345&gclid=67890&id=99"
    expected = "https://site.com/product?id=99"
    assert canonicalize_url(raw) == expected


def test_canonicalize_canonical_tag_override():
    raw = "https://site.com/page?variant=2"
    canonical_tag = "https://site.com/page"
    assert (
        canonicalize_url(raw, canonical_link_tag=canonical_tag)
        == "https://site.com/page"
    )


def test_canonicalize_upgrades_known_secure_discovery_domains():
    assert (
        canonicalize_url("http://arxiv.org/abs/2309.15217v2")
        == "https://arxiv.org/abs/2309.15217v2"
    )
