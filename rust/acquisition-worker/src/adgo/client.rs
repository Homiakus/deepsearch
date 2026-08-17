use crate::error::AcquisitionError;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkToken {
    #[serde(rename = "executionId")]
    pub execution_id: String,
    #[serde(rename = "taskId")]
    pub task_id: String,
    #[serde(rename = "workerId")]
    pub worker_id: String,
    pub attempt: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerSpec {
    pub id: String,
    pub activities: Vec<String>,
    pub concurrency: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteNode {
    pub id: String,
    pub activity: String,
    pub capability: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteActivityRequest {
    pub input: serde_json::Value,
    #[serde(default)]
    pub permissions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteWorkItem {
    pub token: WorkToken,
    pub activity: String,
    pub node: RemoteNode,
    pub request: RemoteActivityRequest,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteFailure {
    pub failure_class: String,
    pub message: String,
    #[serde(default, rename = "retryAfterNanos")]
    pub retry_after_nanos: u64,
}

#[derive(Debug, Clone)]
pub struct AdgoWorkerClient {
    base_url: String,
    token: Option<String>,
    client: Client,
}

impl AdgoWorkerClient {
    pub fn new(base_url: &str, token: Option<String>) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .unwrap_or_else(|_| Client::new());

        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            token,
            client,
        }
    }

    pub async fn poll(
        &self,
        spec: &WorkerSpec,
    ) -> Result<Option<RemoteWorkItem>, AcquisitionError> {
        let url = format!("{}/v1/adgo/workers/poll", self.base_url);
        let mut req = self.client.post(&url).json(spec);
        if let Some(ref tok) = self.token {
            req = req.bearer_auth(tok);
        }

        let resp = req
            .send()
            .await
            .map_err(|e| AcquisitionError::AdgoError(e.to_string()))?;
        if resp.status().as_u16() == 204 {
            return Ok(None);
        }
        if !resp.status().is_success() {
            return Err(AcquisitionError::AdgoError(format!(
                "Poll failed with status: {}",
                resp.status()
            )));
        }

        let item = resp
            .json::<RemoteWorkItem>()
            .await
            .map_err(|e| AcquisitionError::AdgoError(e.to_string()))?;
        Ok(Some(item))
    }

    pub async fn complete(
        &self,
        token: &WorkToken,
        data: serde_json::Value,
        duration_nanos: u64,
    ) -> Result<bool, AcquisitionError> {
        let url = format!("{}/v1/adgo/workers/complete", self.base_url);
        let payload = serde_json::json!({
            "token": token,
            "result": {
                "data": data,
                "usage": { "cost": 1.0 },
                "quality": { "success_rate": 1.0 }
            },
            "durationNanos": duration_nanos
        });

        let mut req = self.client.post(&url).json(&payload);
        if let Some(ref tok) = self.token {
            req = req.bearer_auth(tok);
        }

        let resp = req
            .send()
            .await
            .map_err(|e| AcquisitionError::AdgoError(e.to_string()))?;
        Ok(resp.status().is_success())
    }

    pub async fn fail(
        &self,
        token: &WorkToken,
        failure: &RemoteFailure,
        duration_nanos: u64,
    ) -> Result<bool, AcquisitionError> {
        let url = format!("{}/v1/adgo/workers/fail", self.base_url);
        let payload = serde_json::json!({
            "token": token,
            "failure": failure,
            "durationNanos": duration_nanos
        });

        let mut req = self.client.post(&url).json(&payload);
        if let Some(ref tok) = self.token {
            req = req.bearer_auth(tok);
        }

        let resp = req
            .send()
            .await
            .map_err(|e| AcquisitionError::AdgoError(e.to_string()))?;
        Ok(resp.status().is_success())
    }
}
