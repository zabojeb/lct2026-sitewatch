use std::sync::Arc;

use anyhow::Result;
use sitewatch_api::{AppState, build_router};
use sitewatch_platform::{AppConfig, Infrastructure, init_telemetry};
use tokio::net::TcpListener;
use tracing::info;

#[tokio::main]
async fn main() -> Result<()> {
    init_telemetry();
    let config = AppConfig::from_env()?;
    let infrastructure = Arc::new(Infrastructure::connect(&config).await?);
    let app = build_router(AppState { infrastructure });
    let listener = TcpListener::bind(config.http_addr).await?;

    info!(
        service = %config.app_name,
        environment = %config.app_env,
        address = %config.http_addr,
        "sitewatch API started"
    );

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }
}
