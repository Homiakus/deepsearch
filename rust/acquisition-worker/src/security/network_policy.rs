use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkPolicy {
    pub allow_http: bool,
    pub allow_https: bool,
    pub allowed_hosts: Vec<String>,
    pub denied_hosts: Vec<String>,
    pub allow_private_networks: bool,
    pub max_redirects: usize,
    pub max_body_bytes: usize,
    pub max_subresource_bytes: usize,
    pub max_total_bytes: usize,
    pub allow_websocket: bool,
    pub allow_downloads: bool,
}

impl Default for NetworkPolicy {
    fn default() -> Self {
        Self {
            allow_http: true,
            allow_https: true,
            allowed_hosts: Vec::new(),
            denied_hosts: Vec::new(),
            allow_private_networks: false,
            max_redirects: 5,
            max_body_bytes: 25 * 1024 * 1024,
            max_subresource_bytes: 50 * 1024 * 1024,
            max_total_bytes: 100 * 1024 * 1024,
            allow_websocket: false,
            allow_downloads: false,
        }
    }
}
