"""Unit tests for 3-Level Deduplication Engine (§17)."""

from scraper.normalization.deduplicator import Deduplicator


def test_url_deduplication():
    dedup = Deduplicator()
    url = "http://example.com/page1"
    assert dedup.is_url_duplicate(url) is False
    assert dedup.is_url_duplicate(url) is True


def test_content_deduplication():
    dedup = Deduplicator()
    content = b"<html><body>Hello World</body></html>"
    assert dedup.is_content_duplicate(content) is False
    assert dedup.is_content_duplicate(content) is True


def test_simhash_near_duplicate():
    dedup = Deduplicator(simhash_distance_threshold=3)
    text1 = "The quick brown fox jumps over the lazy dog"
    text2 = "The quick brown fox jumps over the lazy dog!"
    text3 = "Unrelated article about quantum mechanics and particle physics"

    assert dedup.is_near_duplicate(text1) is False
    assert dedup.is_near_duplicate(text2) is True
    assert dedup.is_near_duplicate(text3) is False
