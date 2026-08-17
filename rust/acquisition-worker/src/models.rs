use crate::capabilities::BrowserCapabilities;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtifactReference {
    pub content_hash: String,
    pub uri: String,
    #[serde(default = "default_media_type")]
    pub media_type: String,
    #[serde(default)]
    pub size_bytes: usize,
    #[serde(default)]
    pub metadata_hash: Option<String>,
}

fn default_media_type() -> String {
    "text/html".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct QualityReport {
    #[serde(default = "default_quality_score")]
    pub score: f64,
    #[serde(default = "default_quality_score")]
    pub completeness: f64,
    #[serde(default)]
    pub blocked: bool,
    #[serde(default)]
    pub likely_unrendered: bool,
    #[serde(default)]
    pub reasons: Vec<String>,
    #[serde(default)]
    pub suggested_escalation: Option<String>,
}

fn default_quality_score() -> f64 {
    1.0
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CostReport {
    #[serde(default = "default_base_cost")]
    pub base_cost: f64,
    #[serde(default)]
    pub execution_time_ms: f64,
    #[serde(default)]
    pub memory_mb: f64,
    #[serde(default)]
    pub network_bytes: usize,
    #[serde(default)]
    pub cpu_time_ms: f64,
}

fn default_base_cost() -> f64 {
    1.0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FailureRecord {
    pub failure_class: String,
    pub message: String,
    #[serde(default)]
    pub retryable: bool,
    #[serde(default)]
    pub retry_after_seconds: Option<f64>,
    #[serde(default)]
    pub timestamp: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquisitionRequest {
    pub url: String,
    #[serde(default)]
    pub canonical_url: Option<String>,
    #[serde(default)]
    pub required_capabilities: BrowserCapabilities,
    #[serde(default)]
    pub optional_capabilities: Option<BrowserCapabilities>,
    #[serde(default = "default_mode")]
    pub mode: String,
    #[serde(default = "default_budget")]
    pub budget_max_ms: f64,
    #[serde(default)]
    pub security_context: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub session_ref: Option<String>,
    #[serde(default)]
    pub wait_condition: Option<String>,
    #[serde(default)]
    pub artifact_policy: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub trace_context: HashMap<String, String>,
}

fn default_mode() -> String {
    "balanced".to_string()
}
fn default_budget() -> f64 {
    30000.0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquisitionResult {
    pub requested_url: String,
    pub final_url: String,
    pub backend: String,
    #[serde(default = "default_version")]
    pub backend_version: String,
    pub status_code: u16,
    #[serde(default)]
    pub headers: HashMap<String, String>,
    #[serde(default = "default_media_type")]
    pub content_type: String,
    #[serde(default)]
    pub raw_content: Option<Vec<u8>>,
    #[serde(default)]
    pub text_preview: String,
    #[serde(default)]
    pub artifact_refs: Vec<ArtifactReference>,
    #[serde(default)]
    pub screenshot_bytes: Option<Vec<u8>>,
    #[serde(default)]
    pub network_summary: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub quality: QualityReport,
    #[serde(default)]
    pub cost: CostReport,
    #[serde(default)]
    pub failure: Option<FailureRecord>,
    #[serde(default)]
    pub elapsed_sec: f64,
    #[serde(default)]
    pub capabilities_used: Vec<String>,
}

fn default_version() -> String {
    "1.0.0".to_string()
}

/// Axiom ADGO Batch Activity Models (DS-RB28)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquireBatchInput {
    pub run_id: String,
    pub batch_id: String,
    pub urls: Vec<String>,
    #[serde(default)]
    pub required_capabilities: Option<BrowserCapabilities>,
    #[serde(default = "default_mode")]
    pub mode: String,
    #[serde(default)]
    pub cas_storage_dir: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquireBatchOutput {
    pub results: Vec<AcquisitionResult>,
    pub total_acquired: usize,
    pub success_count: usize,
    pub failure_count: usize,
    pub total_bytes: usize,
    pub total_duration_sec: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct HeartbeatProgress {
    pub processed: usize,
    pub successful: usize,
    pub failed: usize,
    pub current_backend_counts: HashMap<String, usize>,
    pub bytes_downloaded: usize,
    pub browser_seconds: f64,
    pub estimated_remaining_seconds: f64,
}
