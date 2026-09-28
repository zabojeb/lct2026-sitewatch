use std::{env, net::SocketAddr};

use anyhow::{Context, Result, bail};
use sha2::{Digest, Sha256};
use sitewatch_deviations::{AppState, router};
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("sitewatch_deviations=info,tower_http=info")),
        )
        .init();
    let token =
        env::var("SITEWATCH_INTERNAL_TOKEN").context("SITEWATCH_INTERNAL_TOKEN is required")?;
    if token.len() < 32 {
        bail!("SITEWATCH_INTERNAL_TOKEN must contain at least 32 bytes");
    }
    let address: SocketAddr = env::var("DEVIATIONS_HTTP_ADDR")
        .unwrap_or_else(|_| "0.0.0.0:8084".into())
        .parse()
        .context("invalid DEVIATIONS_HTTP_ADDR")?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    tracing::info!(%address, "deviations preview service listening");
    axum::serve(
        listener,
        router(AppState {
            internal_token_sha256: Sha256::digest(token.as_bytes()).into(),
        }),
    )
    .with_graceful_shutdown(shutdown_signal())
    .await
    .context("deviations HTTP server failed")
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{SignalKind, signal};

        if let Ok(mut sigterm) = signal(SignalKind::terminate()) {
            tokio::select! {
                _ = tokio::signal::ctrl_c() => {},
                _ = sigterm.recv() => {},
            }
            return;
        }
    }
    let _ = tokio::signal::ctrl_c().await;
}
