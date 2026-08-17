use acquisition_worker::create_default_registry;
use acquisition_worker::models::AcquisitionRequest;
use std::collections::HashMap;

#[tokio::test]
async fn test_cancellation_and_invalid_scheme_handling() {
    let registry = create_default_registry();
    let http_backend = registry.get("http-standard").expect("http backend missing");

    let req = AcquisitionRequest {
        url: "ftp://invalid-scheme.org/file".to_string(),
        canonical_url: None,
        required_capabilities: Default::default(),
        optional_capabilities: None,
        mode: "fast".to_string(),
        budget_max_ms: 5000.0,
        security_context: HashMap::new(),
        session_ref: None,
        wait_condition: None,
        artifact_policy: HashMap::new(),
        trace_context: HashMap::new(),
    };

    let result = http_backend.acquire(&req).await;
    assert!(result.is_err());
    let err = result.err().unwrap();
    assert_eq!(err.failure_class(), "security");
    assert!(!err.is_retryable());
}
