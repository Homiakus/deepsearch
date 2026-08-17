use acquisition_worker::quality::QualityEvaluator;
use std::collections::HashMap;

#[test]
fn test_quality_clean_html_page() {
    let evaluator = QualityEvaluator::new();
    let headers = HashMap::new();
    let html = "<html><head><title>Test Page</title></head><body><h1>Main Heading</h1><p>This is a complete content paragraph containing enough words to satisfy text length thresholds.</p></body></html>";

    let report = evaluator.evaluate("https://example.com", 200, &headers, html, 50);
    assert_eq!(report.score, 1.0);
    assert_eq!(report.completeness, 1.0);
    assert!(!report.blocked);
    assert!(!report.likely_unrendered);
    assert!(report.suggested_escalation.is_none());
}

#[test]
fn test_quality_detects_block_page() {
    let evaluator = QualityEvaluator::new();
    let headers = HashMap::new();
    let html = "<html><body><h1>Attention Required! | Cloudflare</h1><p>Please complete security check to access.</p></body></html>";

    let report = evaluator.evaluate("https://example.com", 200, &headers, html, 50);
    assert!(report.blocked);
    assert!(report.score < 0.6);
    assert_eq!(report.suggested_escalation.as_deref(), Some("chromium"));
}

#[test]
fn test_quality_detects_empty_spa_root() {
    let evaluator = QualityEvaluator::new();
    let headers = HashMap::new();
    let html = r#"<!DOCTYPE html><html><head><title>App</title></head><body><div id="root"></div><script src="/bundle.js"></script></body></html>"#;

    let report = evaluator.evaluate("https://example.com", 200, &headers, html, 50);
    assert!(report.likely_unrendered);
    assert!(report.score < 0.7);
    assert_eq!(report.suggested_escalation.as_deref(), Some("servo"));
}
