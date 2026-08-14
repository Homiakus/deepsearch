"""Unit tests for Self-Healing Selectors (§60)."""

from selectolax.parser import HTMLParser
from scraper.extraction.self_healing import SelfHealingSelector, ElementFingerprint


def test_self_healing_selector_fallback():
    # Original HTML had div.price-tag
    original_html = '<div class="product"><span class="price-tag">Price: $100</span></div>'
    parser = HTMLParser(original_html)
    node = parser.css_first("span.price-tag")
    fp = SelfHealingSelector.create_fingerprint(node)

    # Modified HTML where class changed from price-tag to amount-label
    modified_html = '<div class="product"><span class="amount-label">Price: $100</span></div>'

    # Primary selector breaks, but self-healing fingerprint matches the node
    matched_node = SelfHealingSelector.match_element(modified_html, "span.price-tag", fingerprint=fp)
    assert matched_node is not None
    assert "Price: $100" in matched_node.text()
