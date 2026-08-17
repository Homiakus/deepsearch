use crate::backends::AcquisitionBackend;
use crate::capabilities::{BackendDescriptor, BrowserCapabilities};
use crate::error::AcquisitionError;
use crate::models::{AcquisitionRequest, AcquisitionResult, CostReport, FailureRecord};
use crate::quality::QualityEvaluator;
use crate::security::UrlPolicy;
use async_trait::async_trait;
use reqwest::header::HeaderMap;
use std::collections::HashMap;
use std::time::Instant;

pub struct HttpBackend {
    descriptor: BackendDescriptor,
    client: reqwest::Client,
    quality_evaluator: QualityEvaluator,
    max_body_bytes: usize,
}

impl Default for HttpBackend {
    fn default() -> Self {
        Self::new("DeepSearch-Acquisition-Worker/1.0", 30, 25 * 1024 * 1024)
    }
}

impl HttpBackend {
    pub fn new(user_agent: &str, timeout_secs: u64, max_body_bytes: usize) -> Self {
        let client = reqwest::Client::builder()
            .user_agent(user_agent)
            .timeout(std::time::Duration::from_secs(timeout_secs))
            .redirect(reqwest::redirect::Policy::limited(5))
            .gzip(true)
            .brotli(true)
            .deflate(true)
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());

        let descriptor = BackendDescriptor {
            name: "http-standard".to_string(),
            version: "1.0.0".to_string(),
            engine_family: "http".to_string(),
            capabilities: BrowserCapabilities::minimal_http(),
            experimental: false,
            base_cost: 1.0,
            startup_cost: 0.0,
            memory_class: "low".to_string(),
            concurrency_class: "high".to_string(),
            security_profile: "strict".to_string(),
            max_concurrency: 64,
        };

        Self {
            descriptor,
            client,
            quality_evaluator: QualityEvaluator::new(),
            max_body_bytes,
        }
    }
}

#[async_trait]
impl AcquisitionBackend for HttpBackend {
    fn descriptor(&self) -> &BackendDescriptor {
        &self.descriptor
    }

    async fn acquire(
        &self,
        req: &AcquisitionRequest,
    ) -> Result<AcquisitionResult, AcquisitionError> {
        let start = Instant::now();

        // 1. SSRF pre-validation
        let valid_url = UrlPolicy::validate_url(&req.url)?;

        // 2. Execute HTTP GET
        let response = match self.client.get(valid_url.as_str()).send().await {
            Ok(resp) => resp,
            Err(e) => {
                let elapsed = start.elapsed().as_secs_f64();
                return Ok(AcquisitionResult {
                    requested_url: req.url.clone(),
                    final_url: req.url.clone(),
                    backend: self.descriptor.name.clone(),
                    backend_version: self.descriptor.version.clone(),
                    status_code: 500,
                    headers: HashMap::new(),
                    content_type: "text/html".to_string(),
                    raw_content: None,
                    text_preview: String::new(),
                    artifact_refs: Vec::new(),
                    screenshot_bytes: None,
                    network_summary: HashMap::new(),
                    quality: Default::default(),
                    cost: CostReport {
                        base_cost: self.descriptor.base_cost,
                        execution_time_ms: elapsed * 1000.0,
                        memory_mb: 2.0,
                        network_bytes: 0,
                        cpu_time_ms: 1.0,
                    },
                    failure: Some(FailureRecord {
                        failure_class: if e.is_timeout() {
                            "transient".to_string()
                        } else {
                            "http_error".to_string()
                        },
                        message: e.to_string(),
                        retryable: e.is_timeout() || e.is_connect(),
                        retry_after_seconds: None,
                        timestamp: 0.0,
                    }),
                    elapsed_sec: elapsed,
                    capabilities_used: vec!["html".to_string()],
                });
            }
        };

        let status = response.status().as_u16();
        let final_url = response.url().to_string();

        let mut headers_map = HashMap::new();
        let header_ref: &HeaderMap = response.headers();
        for (k, v) in header_ref.iter() {
            if let Ok(val_str) = v.to_str() {
                headers_map.insert(k.to_string(), val_str.to_string());
            }
        }

        let content_type = headers_map
            .get("content-type")
            .cloned()
            .unwrap_or_else(|| "text/html".to_string());

        let raw_bytes = match response.bytes().await {
            Ok(b) => {
                if b.len() > self.max_body_bytes {
                    b.slice(..self.max_body_bytes).to_vec()
                } else {
                    b.to_vec()
                }
            }
            Err(e) => {
                let elapsed = start.elapsed().as_secs_f64();
                return Ok(AcquisitionResult {
                    requested_url: req.url.clone(),
                    final_url,
                    backend: self.descriptor.name.clone(),
                    backend_version: self.descriptor.version.clone(),
                    status_code: status,
                    headers: headers_map,
                    content_type,
                    raw_content: None,
                    text_preview: String::new(),
                    artifact_refs: Vec::new(),
                    screenshot_bytes: None,
                    network_summary: HashMap::new(),
                    quality: Default::default(),
                    cost: CostReport {
                        base_cost: self.descriptor.base_cost,
                        execution_time_ms: elapsed * 1000.0,
                        memory_mb: 2.0,
                        network_bytes: 0,
                        cpu_time_ms: 1.0,
                    },
                    failure: Some(FailureRecord {
                        failure_class: "read_error".to_string(),
                        message: e.to_string(),
                        retryable: true,
                        retry_after_seconds: None,
                        timestamp: 0.0,
                    }),
                    elapsed_sec: elapsed,
                    capabilities_used: vec!["html".to_string()],
                });
            }
        };

        let elapsed = start.elapsed().as_secs_f64();
        let text_content = String::from_utf8_lossy(&raw_bytes).to_string();
        let preview = if text_content.len() > 500 {
            text_content[..500].to_string()
        } else {
            text_content.clone()
        };

        let quality =
            self.quality_evaluator
                .evaluate(&final_url, status, &headers_map, &text_content, 100);

        let cost = CostReport {
            base_cost: self.descriptor.base_cost,
            execution_time_ms: elapsed * 1000.0,
            memory_mb: 4.0,
            network_bytes: raw_bytes.len(),
            cpu_time_ms: 2.0,
        };

        Ok(AcquisitionResult {
            requested_url: req.url.clone(),
            final_url,
            backend: self.descriptor.name.clone(),
            backend_version: self.descriptor.version.clone(),
            status_code: status,
            headers: headers_map,
            content_type,
            raw_content: Some(raw_bytes),
            text_preview: preview,
            artifact_refs: Vec::new(),
            screenshot_bytes: None,
            network_summary: HashMap::new(),
            quality,
            cost,
            failure: None,
            elapsed_sec: elapsed,
            capabilities_used: vec!["html".to_string()],
        })
    }
}
