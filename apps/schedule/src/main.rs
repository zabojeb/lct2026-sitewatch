use std::{env, net::SocketAddr};

use anyhow::{Context, Result, bail};
use sha2::{Digest, Sha256};
use sitewatch_schedule::{AppState, outbox, router};
use sqlx::postgres::PgPoolOptions;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("sitewatch_schedule=info,tower_http=info")),
        )
        .init();

    let database_url =
        env::var("SCHEDULE_DATABASE_URL").context("SCHEDULE_DATABASE_URL is required")?;
    let token =
        env::var("SITEWATCH_INTERNAL_TOKEN").context("SITEWATCH_INTERNAL_TOKEN is required")?;
    if token.len() < 32 {
        bail!("SITEWATCH_INTERNAL_TOKEN must contain at least 32 bytes");
    }
    let token_sha256: [u8; 32] = Sha256::digest(token.as_bytes()).into();
    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect(&database_url)
        .await?;
    let nats_url = env::var("NATS_URL").context("NATS_URL is required")?;
    let nats = async_nats::connect(&nats_url)
        .await
        .context("connecting to NATS")?;
    let jetstream = async_nats::jetstream::new(nats);
    jetstream
        .get_stream("SITEWATCH_EVENTS")
        .await
        .context("SITEWATCH_EVENTS JetStream stream must exist")?;

    let address: SocketAddr = env::var("SCHEDULE_HTTP_ADDR")
        .unwrap_or_else(|_| "0.0.0.0:8082".into())
        .parse()
        .context("invalid SCHEDULE_HTTP_ADDR")?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    tracing::info!(%address, "schedule service listening");
    let outbox_task = tokio::spawn(outbox::run(pool.clone(), jetstream.clone()));
    let result = axum::serve(
        listener,
        router(AppState {
            pool,
            jetstream,
            internal_token_sha256: token_sha256,
        }),
    )
    .with_graceful_shutdown(shutdown_signal())
    .await;
    outbox_task.abort();
    result.context("schedule HTTP server failed")
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
