use crate::models::{ArtifactReference, CostReport, QualityReport};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquisitionManifest {
    pub request_id: String,
    pub requested_url: String,
    pub final_url: String,
    pub backend: String,
    pub backend_version: String,
    pub status_code: u16,
    pub headers: HashMap<String, String>,
    pub content_ref: Option<ArtifactReference>,
    pub screenshot_ref: Option<ArtifactReference>,
    pub quality_report: QualityReport,
    pub cost_report: CostReport,
    pub started_at_epoch_ms: u64,
    pub finished_at_epoch_ms: u64,
    pub trace_id: Option<String>,
}
