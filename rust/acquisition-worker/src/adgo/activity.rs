use crate::adgo::heartbeat::HeartbeatManager;
use crate::artifacts::CasArtifactWriter;
use crate::backends::BackendRegistry;
use crate::capabilities::BrowserCapabilities;
use crate::error::AcquisitionError;
use crate::models::{AcquireBatchInput, AcquireBatchOutput, AcquisitionRequest, AcquisitionResult};
use crate::planner::BackendPlanner;
use std::sync::Arc;
use std::time::Instant;

pub struct AcquireBatchActivityHandler {
    registry: Arc<BackendRegistry>,
    planner: Arc<BackendPlanner>,
    cas_writer: Arc<CasArtifactWriter>,
    heartbeat: Arc<HeartbeatManager>,
}

impl AcquireBatchActivityHandler {
    pub fn new(
        registry: Arc<BackendRegistry>,
        planner: Arc<BackendPlanner>,
        cas_writer: Arc<CasArtifactWriter>,
        heartbeat: Arc<HeartbeatManager>,
    ) -> Self {
        Self {
            registry,
            planner,
            cas_writer,
            heartbeat,
        }
    }

    pub async fn execute_batch(
        &self,
        input: AcquireBatchInput,
    ) -> Result<AcquireBatchOutput, AcquisitionError> {
        let start_time = Instant::now();
        let mut results = Vec::new();
        let mut success_count = 0;
        let mut failure_count = 0;
        let mut total_bytes = 0;

        let required_caps = input
            .required_capabilities
            .unwrap_or_else(BrowserCapabilities::minimal_http);
        let available_descriptors = self.registry.descriptors();

        for url in input.urls {
            let req = AcquisitionRequest {
                url: url.clone(),
                canonical_url: None,
                required_capabilities: required_caps.clone(),
                optional_capabilities: None,
                mode: input.mode.clone(),
                budget_max_ms: 30000.0,
                security_context: Default::default(),
                session_ref: None,
                wait_condition: None,
                artifact_policy: Default::default(),
                trace_context: Default::default(),
            };

            // 1. Select backend via planner
            let selected_desc = match self.planner.select_backend(&req, &available_descriptors) {
                Some(d) => d,
                None => {
                    failure_count += 1;
                    results.push(AcquisitionResult {
                        requested_url: url.clone(),
                        final_url: url.clone(),
                        backend: "none".to_string(),
                        backend_version: "1.0.0".to_string(),
                        status_code: 500,
                        headers: Default::default(),
                        content_type: "text/html".to_string(),
                        raw_content: None,
                        text_preview: String::new(),
                        artifact_refs: Vec::new(),
                        screenshot_bytes: None,
                        network_summary: Default::default(),
                        quality: Default::default(),
                        cost: Default::default(),
                        failure: Some(crate::models::FailureRecord {
                            failure_class: "unsupported_capability".to_string(),
                            message: "No backend satisfying required capabilities available"
                                .to_string(),
                            retryable: false,
                            retry_after_seconds: None,
                            timestamp: 0.0,
                        }),
                        elapsed_sec: 0.0,
                        capabilities_used: Vec::new(),
                    });
                    continue;
                }
            };

            let backend = match self.registry.get(&selected_desc.name) {
                Some(b) => b,
                None => continue,
            };

            // 2. Initial acquisition attempt
            let mut result = match backend.acquire(&req).await {
                Ok(res) => res,
                Err(e) => {
                    failure_count += 1;
                    self.heartbeat.update_progress(false, 0, 0.0).await;
                    results.push(AcquisitionResult {
                        requested_url: url.clone(),
                        final_url: url.clone(),
                        backend: selected_desc.name.clone(),
                        backend_version: selected_desc.version.clone(),
                        status_code: 500,
                        headers: Default::default(),
                        content_type: "text/html".to_string(),
                        raw_content: None,
                        text_preview: String::new(),
                        artifact_refs: Vec::new(),
                        screenshot_bytes: None,
                        network_summary: Default::default(),
                        quality: Default::default(),
                        cost: Default::default(),
                        failure: Some(crate::models::FailureRecord {
                            failure_class: e.failure_class().to_string(),
                            message: e.to_string(),
                            retryable: e.is_retryable(),
                            retry_after_seconds: None,
                            timestamp: 0.0,
                        }),
                        elapsed_sec: 0.0,
                        capabilities_used: Vec::new(),
                    });
                    continue;
                }
            };

            // 3. Quality evaluation & escalation check
            let (should_escalate, escalation_backend_desc) =
                self.planner
                    .should_escalate(&result, &selected_desc, &available_descriptors);

            if should_escalate {
                if let Some(esc_desc) = escalation_backend_desc {
                    if let Some(esc_backend) = self.registry.get(&esc_desc.name) {
                        tracing::info!(
                            "Escalating acquisition of {} from {} to {}",
                            url,
                            selected_desc.name,
                            esc_desc.name
                        );
                        if let Ok(escalated_res) = esc_backend.acquire(&req).await {
                            result = escalated_res;
                        }
                    }
                }
            }

            // 4. Offload heavy content to CAS and record ArtifactReference (DS-RB26)
            if let Some(raw) = result.raw_content.take() {
                total_bytes += raw.len();
                if let Ok(art_ref) = self.cas_writer.write_artifact(&raw, &result.content_type) {
                    result.artifact_refs.push(art_ref);
                }
            }

            if let Some(screenshot) = result.screenshot_bytes.take() {
                total_bytes += screenshot.len();
                if let Ok(art_ref) = self.cas_writer.write_artifact(&screenshot, "image/png") {
                    result.artifact_refs.push(art_ref);
                }
            }

            if result.status_code < 400 && result.failure.is_none() {
                success_count += 1;
                self.heartbeat
                    .update_progress(true, result.cost.network_bytes, result.elapsed_sec)
                    .await;
            } else {
                failure_count += 1;
                self.heartbeat
                    .update_progress(false, result.cost.network_bytes, result.elapsed_sec)
                    .await;
            }

            results.push(result);
        }

        let total_duration = start_time.elapsed().as_secs_f64();
        let total_acquired = results.len();

        Ok(AcquireBatchOutput {
            results,
            total_acquired,
            success_count,
            failure_count,
            total_bytes,
            total_duration_sec: total_duration,
        })
    }
}
