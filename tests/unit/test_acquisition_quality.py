"""Unit tests for AcquisitionQualityEvaluator (DS-RB05, DS-RB41)."""

from scraper.acquisition.quality import AcquisitionQualityEvaluator


def test_quality_evaluator_valid_page():
    evaluator = AcquisitionQualityEvaluator()
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Research Article</title></head>
    <body>
        <h1>Deep Learning Research</h1>
        <p>This is a substantive article about artificial intelligence and deep neural network architectures.</p>
        <p>It contains multiple paragraphs with detailed factual text and references.</p>
    </body>
    </html>
    """
    report = evaluator.evaluate(
        url="https://example.com/article",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        html_or_text=html,
        expected_min_text_chars=50,
    )

    assert report.score >= 0.9
    assert report.completeness >= 0.9
    assert not report.blocked
    assert not report.likely_unrendered
    assert report.suggested_escalation is None


def test_quality_evaluator_cloudflare_challenge():
    evaluator = AcquisitionQualityEvaluator()
    html = "<html><body><h1>Attention Required! | Cloudflare</h1><p>Please enable Cookies and reload.</p></body></html>"
    report = evaluator.evaluate(
        url="https://example.com/challenge",
        status_code=403,
        headers={"content-type": "text/html"},
        html_or_text=html,
        expected_min_text_chars=100,
    )

    assert report.blocked is True
    assert report.score <= 0.5
    assert report.suggested_escalation == "chromium"


def test_quality_evaluator_empty_spa_shell():
    evaluator = AcquisitionQualityEvaluator()
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>App</title></head>
    <body>
        <div id="root"></div>
        <noscript>You need to enable JavaScript to run this app.</noscript>
        <script src="/static/js/main.chunk.js"></script>
    </body>
    </html>
    """
    report = evaluator.evaluate(
        url="https://example.com/app",
        status_code=200,
        headers={"content-type": "text/html"},
        html_or_text=html,
        expected_min_text_chars=100,
    )

    assert report.likely_unrendered is True
    assert report.completeness <= 0.3
    assert report.suggested_escalation == "servo"
