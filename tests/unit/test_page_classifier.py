"""Unit tests for Page Intelligence Engine (§7)."""

from scraper.acquisition.page_classifier import classify_page


def test_classify_json_content():
    pi = classify_page(
        "https://api.example.com/data",
        200,
        {"content-type": "application/json"},
        '{"key": "val"}',
    )
    assert pi.content_type == "json"
    assert pi.static_score == 1.0
    assert pi.js_dependency_score == 0.0
    assert pi.api_score == 1.0


def test_classify_react_next_page():
    html = """
    <html>
      <head><script id="__NEXT_DATA__">{}</script></head>
      <body><div id="__next"></div></body>
    </html>
    """
    pi = classify_page(
        "https://example.com/next-page", 200, {"content-type": "text/html"}, html
    )
    assert "Next.js" in pi.detected_frameworks
    assert pi.js_dependency_score >= 0.5


def test_classify_bot_block():
    html = "<html><body>403 Forbidden - Cloudflare Captcha required</body></html>"
    pi = classify_page("https://blocked.com", 403, {"content-type": "text/html"}, html)
    assert pi.block_score >= 0.9
