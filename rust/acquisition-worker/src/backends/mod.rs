use crate::capabilities::BackendDescriptor;
use crate::error::AcquisitionError;
use crate::models::{AcquisitionRequest, AcquisitionResult};
use async_trait::async_trait;
use std::collections::HashMap;
use std::sync::Arc;

#[async_trait]
pub trait AcquisitionBackend: Send + Sync {
    fn descriptor(&self) -> &BackendDescriptor;
    async fn acquire(
        &self,
        req: &AcquisitionRequest,
    ) -> Result<AcquisitionResult, AcquisitionError>;
}

pub struct BackendRegistry {
    backends: HashMap<String, Arc<dyn AcquisitionBackend>>,
}

impl Default for BackendRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl BackendRegistry {
    pub fn new() -> Self {
        Self {
            backends: HashMap::new(),
        }
    }

    pub fn register(&mut self, backend: Arc<dyn AcquisitionBackend>) {
        let name = backend.descriptor().name.clone();
        self.backends.insert(name, backend);
    }

    pub fn get(&self, name: &str) -> Option<Arc<dyn AcquisitionBackend>> {
        self.backends.get(name).cloned()
    }

    pub fn descriptors(&self) -> Vec<BackendDescriptor> {
        self.backends
            .values()
            .map(|b| b.descriptor().clone())
            .collect()
    }

    pub fn available_backends(&self) -> Vec<Arc<dyn AcquisitionBackend>> {
        self.backends.values().cloned().collect()
    }
}

pub mod blitz;
pub mod browseroxide;
pub mod chromium;
pub mod http;
pub mod http_spider;
pub mod servo;
