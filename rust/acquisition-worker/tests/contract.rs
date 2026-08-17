use acquisition_worker::capabilities::{BrowserCapabilities, CapabilityLevel};
use acquisition_worker::models::{
    AcquisitionRequest, AcquisitionResult, ArtifactReference, CostReport, FailureRecord,
    QualityReport,
};
use std::collections::HashMap;

#[test]
fn test_capabilities_bidirectional_serialization() {
    let mut caps = BrowserCapabilities::minimal_http();
    caps.javascript = CapabilityLevel::Supported;
    caps.dom_mutation = CapabilityLevel::Partial;
    caps.screenshot = CapabilityLevel::Supported;

    let json_str = serde_json::to_string(&caps).expect("Serialization failed");
    let deserialized: BrowserCapabilities =
        serde_json::from_str(&json_str).expect("Deserialization failed");

    assert_eq!(caps, deserialized);
    assert_eq!(deserialized.javascript, CapabilityLevel::Supported);
    assert_eq!(deserialized.dom_mutation, CapabilityLevel::Partial);
    assert_eq!(deserialized.screenshot, CapabilityLevel::Supported);
}

#[test]
fn test_acquisition_request_json_contract() {
    let raw_json = r#"{
        "url": "https://example.com/test",
        "canonical_url": "https://example.com/test",
        "required_capabilities": {
            "html": "supported",
            "javascript": "supported",
            "screenshot": "unsupported"
        },
        "mode": "balanced",
        "budget_max_ms": 15000.0,
        "security_context": {},
        "trace_context": {
            "run_id": "run-001"
        }
    }"#;

    let req: AcquisitionRequest =
        serde_json::from_str(raw_json).expect("Failed to parse AcquisitionRequest");
    assert_eq!(req.url, "https://example.com/test");
    assert_eq!(
        req.required_capabilities.javascript,
        CapabilityLevel::Supported
    );
    assert_eq!(
        req.required_capabilities.screenshot,
        CapabilityLevel::Unsupported
    );
    assert_eq!(req.budget_max_ms, 15000.0);
    assert_eq!(req.trace_context.get("run_id").unwrap(), "run-001");
}

#[test]
fn test_acquisition_result_json_contract() {
    let mut headers = HashMap::new();
    headers.insert(
        "content-type".to_string(),
        "text/html; charset=utf-8".to_string(),
    );

    let result = AcquisitionResult {
        requested_url: "https://example.com/start".to_string(),
        final_url: "https://example.com/final".to_string(),
        backend: "servo-offscreen".to_string(),
        backend_version: "1.0.0".to_string(),
        status_code: 200,
        headers,
        content_type: "text/html".to_string(),
        raw_content: None,
        text_preview: "Sample text preview".to_string(),
        artifact_refs: vec![ArtifactReference {
            content_hash: "abcdef123456".to_string(),
            uri: "cas://ab/abcdef123456.html".to_string(),
            media_type: "text/html".to_string(),
            size_bytes: 1024,
            metadata_hash: None,
        }],
        screenshot_bytes: None,
        network_summary: HashMap::new(),
        quality: QualityReport {
            score: 0.95,
            completeness: 1.0,
            blocked: false,
            likely_unrendered: false,
            reasons: vec![],
            suggested_escalation: None,
        },
        cost: CostReport {
            base_cost: 4.0,
            execution_time_ms: 250.0,
            memory_mb: 45.0,
            network_bytes: 1024,
            cpu_time_ms: 12.0,
        },
        failure: None,
        elapsed_sec: 0.25,
        capabilities_used: vec!["html".to_string(), "javascript".to_string()],
    };

    let serialized = serde_json::to_string(&result).expect("Failed to serialize AcquisitionResult");
    let deserialized: AcquisitionResult =
        serde_json::from_str(&serialized).expect("Failed to deserialize AcquisitionResult");

    assert_eq!(deserialized.backend, "servo-offscreen");
    assert_eq!(deserialized.status_code, 200);
    assert_eq!(deserialized.artifact_refs.len(), 1);
    assert_eq!(deserialized.artifact_refs[0].content_hash, "abcdef123456");
    assert_eq!(deserialized.quality.score, 0.95);
}

#[test]
fn test_failure_record_serialization() {
    let failure = FailureRecord {
        failure_class: "rate_limit".to_string(),
        message: "HTTP 429 Too Many Requests".to_string(),
        retryable: true,
        retry_after_seconds: Some(10.0),
        timestamp: 1700000000.0,
    };

    let json_val = serde_json::to_value(&failure).expect("Failed to convert failure to Value");
    assert_eq!(json_val["failure_class"], "rate_limit");
    assert_eq!(json_val["retryable"], true);
    assert_eq!(json_val["retry_after_seconds"], 10.0);
}
