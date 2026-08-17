use crate::backends::http::HttpBackend;
use crate::backends::AcquisitionBackend;
use crate::capabilities::{BackendDescriptor, BrowserCapabilities, CapabilityLevel};
use crate::error::AcquisitionError;
use crate::models::{AcquisitionRequest, AcquisitionResult};
use async_trait::async_trait;

pub struct BrowserOxideBackend {
    descriptor: BackendDescriptor,
    http_fallback: HttpBackend,
}

impl Default for BrowserOxideBackend {
    fn default() -> Self {
        Self::new()
    }
}

impl BrowserOxideBackend {
    pub fn new() -> Self {
        let mut caps = BrowserCapabilities::minimal_http();
        caps.javascript = CapabilityLevel::Partial;
        caps.dom_mutation = CapabilityLevel::Partial;
        caps.css_layout = CapabilityLevel::Supported;

        let descriptor = BackendDescriptor {
            name: "browseroxide-experimental".to_string(),
            version: "0.1.0".to_string(),
            engine_family: "browseroxide".to_string(),
            capabilities: caps,
            experimental: true,
            base_cost: 2.0,
            startup_cost: 0.1,
            memory_class: "low".to_string(),
            concurrency_class: "medium".to_string(),
            security_profile: "experimental".to_string(),
            max_concurrency: 16,
        };

        Self {
            descriptor,
            http_fallback: HttpBackend::new("DeepSearch-BrowserOxide/0.1", 20, 20 * 1024 * 1024),
        }
    }
}

#[async_trait]
impl AcquisitionBackend for BrowserOxideBackend {
    fn descriptor(&self) -> &BackendDescriptor {
        &self.descriptor
    }

    async fn acquire(
        &self,
        req: &AcquisitionRequest,
    ) -> Result<AcquisitionResult, AcquisitionError> {
        let mut res = self.http_fallback.acquire(req).await?;
        res.backend = self.descriptor.name.clone();
        res.backend_version = self.descriptor.version.clone();
        Ok(res)
    }
}
