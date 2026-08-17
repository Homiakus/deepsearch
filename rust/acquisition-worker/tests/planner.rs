use acquisition_worker::capabilities::{BrowserCapabilities, CapabilityLevel};
use acquisition_worker::create_default_registry;
use acquisition_worker::models::{AcquisitionRequest, AcquisitionResult, QualityReport};
use acquisition_worker::planner::BackendPlanner;
use std::collections::HashMap;

#[test]
fn test_planner_selects_http_for_minimal_request() {
    let registry = create_default_registry();
    let descriptors = registry.descriptors();
    let planner = BackendPlanner::default();

    let req = AcquisitionRequest {
        url: "https://example.com/static".to_string(),
        canonical_url: None,
        required_capabilities: BrowserCapabilities::minimal_http(),
        optional_capabilities: None,
        mode: "fast".to_string(),
        budget_max_ms: 10000.0,
        security_context: HashMap::new(),
        session_ref: None,
        wait_condition: None,
        artifact_policy: HashMap::new(),
        trace_context: HashMap::new(),
    };

    let selected = planner
        .select_backend(&req, &descriptors)
        .expect("Failed to select backend");
    assert_eq!(selected.engine_family, "http");
}

#[test]
fn test_planner_selects_servo_when_js_required() {
    let registry = create_default_registry();
    let descriptors = registry.descriptors();
    let planner = BackendPlanner::default();

    let mut req_caps = BrowserCapabilities::minimal_http();
    req_caps.javascript = CapabilityLevel::Supported;
    req_caps.dom_mutation = CapabilityLevel::Supported;

    let req = AcquisitionRequest {
        url: "https://example.com/app".to_string(),
        canonical_url: None,
        required_capabilities: req_caps,
        optional_capabilities: None,
        mode: "balanced".to_string(),
        budget_max_ms: 20000.0,
        security_context: HashMap::new(),
        session_ref: None,
        wait_condition: None,
        artifact_policy: HashMap::new(),
        trace_context: HashMap::new(),
    };

    let selected = planner
        .select_backend(&req, &descriptors)
        .expect("Failed to select backend");
    // Should select lowest-cost JS backend: Servo (base_cost=4.0) rather than Chromium (base_cost=10.0)
    assert_eq!(selected.engine_family, "servo");
}

#[test]
fn test_planner_escalation_rules() {
    let registry = create_default_registry();
    let descriptors = registry.descriptors();
    let planner = BackendPlanner::default();

    let http_desc = descriptors
        .iter()
        .find(|d| d.name == "http-standard")
        .unwrap();

    let blocked_result = AcquisitionResult {
        requested_url: "https://example.com/blocked".to_string(),
        final_url: "https://example.com/blocked".to_string(),
        backend: "http-standard".to_string(),
        backend_version: "1.0.0".to_string(),
        status_code: 403,
        headers: HashMap::new(),
        content_type: "text/html".to_string(),
        raw_content: None,
        text_preview: "Access Denied".to_string(),
        artifact_refs: vec![],
        screenshot_bytes: None,
        network_summary: HashMap::new(),
        quality: QualityReport {
            score: 0.2,
            completeness: 0.1,
            blocked: true,
            likely_unrendered: false,
            reasons: vec!["Rate limit or access forbidden".to_string()],
            suggested_escalation: Some("chromium".to_string()),
        },
        cost: Default::default(),
        failure: None,
        elapsed_sec: 0.1,
        capabilities_used: vec!["html".to_string()],
    };

    let (should_escalate, esc_desc) =
        planner.should_escalate(&blocked_result, http_desc, &descriptors);
    assert!(should_escalate);
    assert_eq!(esc_desc.unwrap().engine_family, "chromium");
}
