use std::net::SocketAddr;
use std::sync::Arc;
use tokio::signal;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use acquisition_worker::{
    artifacts::CasArtifactWriter,
    config::WorkerConfig,
    create_default_registry,
    planner::BackendPlanner,
    service::{create_router, AppState},
    telemetry::DomainTelemetry,
};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "acquisition_worker=info,tower_http=debug".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = WorkerConfig::default();
    tracing::info!(
        "Starting DeepSearch Rust Acquisition Worker [{}]",
        config.worker_id
    );

    let registry = Arc::new(create_default_registry());
    let telemetry = DomainTelemetry::default();
    let planner = Arc::new(BackendPlanner::new(telemetry));
    let cas_writer = Arc::new(CasArtifactWriter::new(&config.cas_dir));

    let state = AppState {
        registry,
        planner,
        cas_writer,
        worker_id: config.worker_id.clone(),
    };

    let app = create_router(state);
    let addr: SocketAddr = format!("{}:{}", config.host, config.port).parse()?;
    tracing::info!("Local API server listening on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    tracing::info!("Rust Acquisition Worker gracefully shut down.");
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
