use crate::backends::http::HttpBackend;
use crate::backends::AcquisitionBackend;
use crate::capabilities::{BackendDescriptor, BrowserCapabilities};
use crate::error::AcquisitionError;
use crate::models::{AcquisitionRequest, AcquisitionResult};
use async_trait::async_trait;

pub struct SpiderBackend {
    descriptor: BackendDescriptor,
    inner_http: HttpBackend,
}

impl Default for SpiderBackend {
    fn default() -> Self {
        Self::new()
    }
}

impl SpiderBackend {
    pub fn new() -> Self {
        let descriptor = BackendDescriptor {
            name: "spider-crawler".to_string(),
            version: "1.0.0".to_string(),
            engine_family: "http".to_string(),
            capabilities: BrowserCapabilities::minimal_http(),
            experimental: true,
            base_cost: 0.8,
            startup_cost: 0.0,
            memory_class: "low".to_string(),
            concurrency_class: "high".to_string(),
            security_profile: "strict".to_string(),
            max_concurrency: 128,
        };

        Self {
            descriptor,
            inner_http: HttpBackend::new("DeepSearch-Spider/1.0", 20, 20 * 1024 * 1024),
        }
    }
}

#[async_trait]
impl AcquisitionBackend for SpiderBackend {
    fn descriptor(&self) -> &BackendDescriptor {
        &self.descriptor
    }

    async fn acquire(
        &self,
        req: &AcquisitionRequest,
    ) -> Result<AcquisitionResult, AcquisitionError> {
        let mut res = self.inner_http.acquire(req).await?;
        res.backend = self.descriptor.name.clone();
        res.backend_version = self.descriptor.version.clone();
        Ok(res)
    }
}
