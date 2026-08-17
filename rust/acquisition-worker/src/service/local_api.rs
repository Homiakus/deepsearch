use crate::artifacts::CasArtifactWriter;
use crate::backends::BackendRegistry;
use crate::models::{AcquisitionRequest, AcquisitionResult};
use crate::planner::BackendPlanner;
use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    pub registry: Arc<BackendRegistry>,
    pub planner: Arc<BackendPlanner>,
    pub cas_writer: Arc<CasArtifactWriter>,
    pub worker_id: String,
}

pub fn create_router(state: AppState) -> Router {
    Router::new()
        .route("/v1/health", get(health_handler))
        .route("/v1/backends", get(backends_handler))
        .route("/v1/metrics", get(metrics_handler))
        .route("/v1/acquire", post(acquire_handler))
        .with_state(state)
}

async fn health_handler(State(state): State<AppState>) -> impl IntoResponse {
    Json(json!({
        "status": "ok",
        "worker_id": state.worker_id,
        "backends_count": state.registry.descriptors().len(),
    }))
}

async fn backends_handler(State(state): State<AppState>) -> impl IntoResponse {
    Json(state.registry.descriptors())
}

async fn metrics_handler(State(state): State<AppState>) -> impl IntoResponse {
    Json(json!({
        "worker_id": state.worker_id,
        "available_backends": state.registry.descriptors().len(),
        "status": "healthy"
    }))
}

async fn acquire_handler(
    State(state): State<AppState>,
    Json(req): Json<AcquisitionRequest>,
) -> Result<Json<AcquisitionResult>, (StatusCode, Json<serde_json::Value>)> {
    let descriptors = state.registry.descriptors();
    let selected = state
        .planner
        .select_backend(&req, &descriptors)
        .ok_or_else(|| {
            (
                StatusCode::BAD_REQUEST,
                Json(json!({
                    "error": "No eligible backend satisfying required capabilities"
                })),
            )
        })?;

    let backend = state.registry.get(&selected.name).ok_or_else(|| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "error": "Selected backend is not available" })),
        )
    })?;

    let mut result = match backend.acquire(&req).await {
        Ok(res) => res,
        Err(e) => {
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({
                    "error": e.to_string(),
                    "failure_class": e.failure_class(),
                })),
            ));
        }
    };

    // Offload content to CAS
    if let Some(raw) = result.raw_content.take() {
        if let Ok(art_ref) = state.cas_writer.write_artifact(&raw, &result.content_type) {
            result.artifact_refs.push(art_ref);
        }
    }

    Ok(Json(result))
}
