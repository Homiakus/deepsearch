use std::collections::HashMap;
use std::sync::{Arc, RwLock};

#[derive(Debug, Clone, Default)]
pub struct DomainStat {
    pub attempts: f64,
    pub successes: f64,
    pub quality_ewma: f64,
    pub latency_ewma: f64,
}

#[derive(Debug, Clone)]
pub struct DomainTelemetry {
    alpha: f64,
    stats: Arc<RwLock<HashMap<(String, String), DomainStat>>>,
}

impl Default for DomainTelemetry {
    fn default() -> Self {
        Self::new(0.2)
    }
}

impl DomainTelemetry {
    pub fn new(alpha: f64) -> Self {
        Self {
            alpha,
            stats: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn record(
        &self,
        domain: &str,
        backend: &str,
        success: bool,
        quality: f64,
        latency_ms: f64,
    ) {
        let key = (domain.to_lowercase(), backend.to_lowercase());
        let mut map = self.stats.write().unwrap();
        let entry = map.entry(key).or_insert_with(|| DomainStat {
            attempts: 0.0,
            successes: 0.0,
            quality_ewma: quality,
            latency_ewma: latency_ms,
        });

        entry.attempts += 1.0;
        if success {
            entry.successes += 1.0;
        }
        entry.quality_ewma = (1.0 - self.alpha) * entry.quality_ewma + self.alpha * quality;
        entry.latency_ewma = (1.0 - self.alpha) * entry.latency_ewma + self.alpha * latency_ms;
    }

    pub fn get_success_probability(&self, domain: &str, backend: &str) -> f64 {
        let key = (domain.to_lowercase(), backend.to_lowercase());
        let map = self.stats.read().unwrap();
        if let Some(entry) = map.get(&key) {
            if entry.attempts < 3.0 {
                return 0.95; // Optimistic prior
            }
            (entry.successes / entry.attempts).clamp(0.05, 0.99)
        } else {
            0.95
        }
    }
}
