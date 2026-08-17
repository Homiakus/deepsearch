pub mod adgo;
pub mod artifacts;
pub mod backends;
pub mod capabilities;
pub mod config;
pub mod error;
pub mod models;
pub mod planner;
pub mod quality;
pub mod security;
pub mod service;
pub mod telemetry;

use crate::backends::{
    blitz::BlitzBackend, browseroxide::BrowserOxideBackend, chromium::ChromiumBackend,
    http::HttpBackend, http_spider::SpiderBackend, servo::ServoBackend, BackendRegistry,
};
use std::sync::Arc;

/// Creates standard registry populated with all configured acquisition backends.
pub fn create_default_registry() -> BackendRegistry {
    let mut registry = BackendRegistry::new();
    registry.register(Arc::new(HttpBackend::default()));
    registry.register(Arc::new(SpiderBackend::default()));
    registry.register(Arc::new(ServoBackend::default()));
    registry.register(Arc::new(ChromiumBackend::default()));
    registry.register(Arc::new(BrowserOxideBackend::default()));
    registry.register(Arc::new(BlitzBackend::default()));
    registry
}
