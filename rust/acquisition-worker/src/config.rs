use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerConfig {
    pub host: String,
    pub port: u16,
    pub adgo_coordinator_url: Option<String>,
    pub adgo_worker_token: Option<String>,
    pub worker_id: String,
    pub concurrency: usize,
    pub cas_dir: String,
    pub user_agent: String,
    pub request_timeout_secs: u64,
    pub max_body_bytes: usize,
    pub max_redirects: usize,
}

impl Default for WorkerConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 8081,
            adgo_coordinator_url: None,
            adgo_worker_token: None,
            worker_id: format!("rust-acquisition-worker-{}", uuid::Uuid::new_v4().simple()),
            concurrency: 16,
            cas_dir: "./data/cas".to_string(),
            user_agent:
                "DeepSearch-Acquisition-Worker/1.0 (+https://github.com/Homiakus/deepsearch)"
                    .to_string(),
            request_timeout_secs: 30,
            max_body_bytes: 25 * 1024 * 1024,
            max_redirects: 5,
        }
    }
}
