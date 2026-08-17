use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum CapabilityLevel {
    #[default]
    Unsupported,
    Partial,
    Supported,
}

impl CapabilityLevel {
    pub fn is_satisfied_by(&self, required: CapabilityLevel) -> bool {
        match required {
            CapabilityLevel::Unsupported => true,
            CapabilityLevel::Partial => {
                matches!(self, CapabilityLevel::Partial | CapabilityLevel::Supported)
            }
            CapabilityLevel::Supported => matches!(self, CapabilityLevel::Supported),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct BrowserCapabilities {
    #[serde(default = "default_supported")]
    pub html: CapabilityLevel,
    #[serde(default)]
    pub javascript: CapabilityLevel,
    #[serde(default)]
    pub dom_mutation: CapabilityLevel,
    #[serde(default)]
    pub css_layout: CapabilityLevel,
    #[serde(default)]
    pub screenshot: CapabilityLevel,
    #[serde(default)]
    pub network_capture: CapabilityLevel,
    #[serde(default)]
    pub cookies: CapabilityLevel,
    #[serde(default)]
    pub local_storage: CapabilityLevel,
    #[serde(default)]
    pub session_persistence: CapabilityLevel,
    #[serde(default)]
    pub iframe: CapabilityLevel,
    #[serde(default)]
    pub shadow_dom: CapabilityLevel,
    #[serde(default)]
    pub websocket: CapabilityLevel,
    #[serde(default)]
    pub service_worker: CapabilityLevel,
    #[serde(default)]
    pub canvas: CapabilityLevel,
    #[serde(default)]
    pub webgl: CapabilityLevel,
    #[serde(default)]
    pub pdf_print: CapabilityLevel,
    #[serde(default)]
    pub file_download: CapabilityLevel,
    #[serde(default)]
    pub user_interaction: CapabilityLevel,
}

fn default_supported() -> CapabilityLevel {
    CapabilityLevel::Supported
}

impl BrowserCapabilities {
    pub fn minimal_http() -> Self {
        Self {
            html: CapabilityLevel::Supported,
            ..Default::default()
        }
    }

    pub fn full_browser() -> Self {
        Self {
            html: CapabilityLevel::Supported,
            javascript: CapabilityLevel::Supported,
            dom_mutation: CapabilityLevel::Supported,
            css_layout: CapabilityLevel::Supported,
            screenshot: CapabilityLevel::Supported,
            network_capture: CapabilityLevel::Supported,
            cookies: CapabilityLevel::Supported,
            local_storage: CapabilityLevel::Supported,
            session_persistence: CapabilityLevel::Supported,
            iframe: CapabilityLevel::Supported,
            shadow_dom: CapabilityLevel::Supported,
            websocket: CapabilityLevel::Supported,
            service_worker: CapabilityLevel::Supported,
            canvas: CapabilityLevel::Supported,
            webgl: CapabilityLevel::Supported,
            pdf_print: CapabilityLevel::Supported,
            file_download: CapabilityLevel::Supported,
            user_interaction: CapabilityLevel::Supported,
        }
    }

    pub fn satisfies(&self, required: &BrowserCapabilities) -> bool {
        self.html.is_satisfied_by(required.html)
            && self.javascript.is_satisfied_by(required.javascript)
            && self.dom_mutation.is_satisfied_by(required.dom_mutation)
            && self.css_layout.is_satisfied_by(required.css_layout)
            && self.screenshot.is_satisfied_by(required.screenshot)
            && self
                .network_capture
                .is_satisfied_by(required.network_capture)
            && self.cookies.is_satisfied_by(required.cookies)
            && self.local_storage.is_satisfied_by(required.local_storage)
            && self
                .session_persistence
                .is_satisfied_by(required.session_persistence)
            && self.iframe.is_satisfied_by(required.iframe)
            && self.shadow_dom.is_satisfied_by(required.shadow_dom)
            && self.websocket.is_satisfied_by(required.websocket)
            && self.service_worker.is_satisfied_by(required.service_worker)
            && self.canvas.is_satisfied_by(required.canvas)
            && self.webgl.is_satisfied_by(required.webgl)
            && self.pdf_print.is_satisfied_by(required.pdf_print)
            && self.file_download.is_satisfied_by(required.file_download)
            && self
                .user_interaction
                .is_satisfied_by(required.user_interaction)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendDescriptor {
    pub name: String,
    pub version: String,
    pub engine_family: String,
    pub capabilities: BrowserCapabilities,
    #[serde(default)]
    pub experimental: bool,
    #[serde(default = "default_base_cost")]
    pub base_cost: f64,
    #[serde(default)]
    pub startup_cost: f64,
    #[serde(default = "default_memory_class")]
    pub memory_class: String,
    #[serde(default = "default_concurrency_class")]
    pub concurrency_class: String,
    #[serde(default = "default_security_profile")]
    pub security_profile: String,
    #[serde(default = "default_max_concurrency")]
    pub max_concurrency: usize,
}

fn default_base_cost() -> f64 {
    1.0
}
fn default_memory_class() -> String {
    "low".to_string()
}
fn default_concurrency_class() -> String {
    "high".to_string()
}
fn default_security_profile() -> String {
    "standard".to_string()
}
fn default_max_concurrency() -> usize {
    16
}
