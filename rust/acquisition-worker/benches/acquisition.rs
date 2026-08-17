// Acquisition Benchmark Suite (DS-RB00)

use acquisition_worker::create_default_registry;
use acquisition_worker::models::AcquisitionRequest;
use std::collections::HashMap;
use std::time::Instant;

#[tokio::main]
async fn main() {
    println!("Running Rust Acquisition Worker local benchmark...");
    let registry = create_default_registry();
    let http = registry.get("http-standard").unwrap();

    let urls = vec![
        "https://httpbin.org/html",
        "https://httpbin.org/gzip",
        "https://httpbin.org/deflate",
    ];

    for url in urls {
        let req = AcquisitionRequest {
            url: url.to_string(),
            canonical_url: None,
            required_capabilities: Default::default(),
            optional_capabilities: None,
            mode: "fast".to_string(),
            budget_max_ms: 10000.0,
            security_context: HashMap::new(),
            session_ref: None,
            wait_condition: None,
            artifact_policy: HashMap::new(),
            trace_context: HashMap::new(),
        };

        let start = Instant::now();
        let res = http.acquire(&req).await;
        let elapsed = start.elapsed();
        match res {
            Ok(r) => println!(
                "Acquired {} in {:?} (status: {})",
                url, elapsed, r.status_code
            ),
            Err(e) => println!("Failed {}: {:?}", url, e),
        }
    }
}
