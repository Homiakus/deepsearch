use crate::backends::http::HttpBackend;
use crate::backends::AcquisitionBackend;
use crate::capabilities::{BackendDescriptor, BrowserCapabilities, CapabilityLevel};
use crate::error::AcquisitionError;
use crate::models::{AcquisitionRequest, AcquisitionResult};
use async_trait::async_trait;

pub struct BlitzBackend {
    descriptor: BackendDescriptor,
    http_fallback: HttpBackend,
}

impl Default for BlitzBackend {
    fn default() -> Self {
        Self::new()
    }
}

impl BlitzBackend {
    pub fn new() -> Self {
        let mut caps = BrowserCapabilities::minimal_http();
        caps.css_layout = CapabilityLevel::Supported;
        caps.screenshot = CapabilityLevel::Supported;
        caps.javascript = CapabilityLevel::Unsupported;

        let descriptor = BackendDescriptor {
            name: "blitz-layout".to_string(),
            version: "1.0.0".to_string(),
            engine_family: "blitz".to_string(),
            capabilities: caps,
            experimental: true,
            base_cost: 1.5,
            startup_cost: 0.1,
            memory_class: "low".to_string(),
            concurrency_class: "high".to_string(),
            security_profile: "strict".to_string(),
            max_concurrency: 32,
        };

        Self {
            descriptor,
            http_fallback: HttpBackend::new("DeepSearch-Blitz/1.0", 20, 20 * 1024 * 1024),
        }
    }
}

#[async_trait]
impl AcquisitionBackend for BlitzBackend {
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
