use crate::capabilities::BackendDescriptor;
use crate::models::{AcquisitionRequest, AcquisitionResult};
use crate::telemetry::DomainTelemetry;
use url::Url;

pub struct BackendPlanner {
    telemetry: DomainTelemetry,
}

impl Default for BackendPlanner {
    fn default() -> Self {
        Self::new(DomainTelemetry::default())
    }
}

impl BackendPlanner {
    pub fn new(telemetry: DomainTelemetry) -> Self {
        Self { telemetry }
    }

    pub fn select_backend(
        &self,
        request: &AcquisitionRequest,
        available_backends: &[BackendDescriptor],
    ) -> Option<BackendDescriptor> {
        if available_backends.is_empty() {
            return None;
        }

        let domain = Url::parse(&request.url)
            .ok()
            .and_then(|u| u.host_str().map(|h| h.to_string()))
            .unwrap_or_else(|| "unknown".to_string());

        // 1. Filter by hard required capabilities
        let eligible: Vec<&BackendDescriptor> = available_backends
            .iter()
            .filter(|desc| desc.capabilities.satisfies(&request.required_capabilities))
            .collect();

        if eligible.is_empty() {
            return None;
        }

        // 2. Score eligible backends by expected cost: base_cost / p_success
        let mut scored: Vec<(f64, &BackendDescriptor)> = eligible
            .into_iter()
            .map(|desc| {
                let p_success = self.telemetry.get_success_probability(&domain, &desc.name);
                let expected_cost = (desc.base_cost + desc.startup_cost * 0.1) / p_success;
                (expected_cost, desc)
            })
            .collect();

        scored.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
        scored.first().map(|(_, desc)| (*desc).clone())
    }

    pub fn should_escalate(
        &self,
        result: &AcquisitionResult,
        current_backend: &BackendDescriptor,
        available_backends: &[BackendDescriptor],
    ) -> (bool, Option<BackendDescriptor>) {
        if result.quality.score >= 0.7
            && !result.quality.blocked
            && !result.quality.likely_unrendered
        {
            return (false, None);
        }

        let mut candidates: Vec<&BackendDescriptor> = available_backends
            .iter()
            .filter(|b| b.name != current_backend.name && b.base_cost >= current_backend.base_cost)
            .collect();

        if let Some(ref suggested) = result.quality.suggested_escalation {
            for b in &candidates {
                if b.engine_family == *suggested || b.name == *suggested {
                    return (true, Some((*b).clone()));
                }
            }
        }

        if !candidates.is_empty() {
            candidates.sort_by(|a, b| a.base_cost.partial_cmp(&b.base_cost).unwrap());
            return (true, Some(candidates[0].clone()));
        }

        (false, None)
    }
}
