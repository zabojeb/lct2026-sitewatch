use std::{env, net::SocketAddr, str::FromStr, time::Instant};

use anyhow::{Context, Result};
use sqlx::{PgPool, postgres::PgPoolOptions};
use tracing_subscriber::{EnvFilter, layer::SubscriberExt, util::SubscriberInitExt};

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub app_env: String,
    pub app_name: String,
    pub http_addr: SocketAddr,
    pub database_url: String,
    pub redis_url: String,
    pub nats_url: String,
}

impl AppConfig {
    /// Loads runtime configuration from environment variables.
    ///
    /// # Errors
    ///
    /// Returns an error when a required variable is missing or `HTTP_ADDR` is malformed.
    pub fn from_env() -> Result<Self> {
        Ok(Self {
            app_env: env_or("APP_ENV", "local"),
            app_name: env_or("APP_NAME", "sitewatch"),
            http_addr: SocketAddr::from_str(&env_or("HTTP_ADDR", "0.0.0.0:8080"))
                .context("HTTP_ADDR must be a valid socket address")?,
            database_url: required_env("DATABASE_URL")?,
            redis_url: required_env("REDIS_URL")?,
            nats_url: required_env("NATS_URL")?,
        })
    }
}

#[derive(Debug, Clone)]
pub struct Infrastructure {
    pub postgres: PgPool,
    pub redis: redis::Client,
    pub nats: async_nats::Client,
}

#[derive(Debug, Clone)]
pub struct DependencyProbe {
    pub name: &'static str,
    pub healthy: bool,
    pub latency_ms: u64,
    pub detail: Option<String>,
}

impl Infrastructure {
    /// Establishes required `PostgreSQL`, Redis and NATS clients.
    ///
    /// # Errors
    ///
    /// Returns an error when a required dependency cannot be configured or reached.
    pub async fn connect(config: &AppConfig) -> Result<Self> {
        let postgres = PgPoolOptions::new()
            .max_connections(20)
            .connect(&config.database_url)
            .await
            .context("failed to connect to PostgreSQL")?;
        let redis = redis::Client::open(config.redis_url.as_str())
            .context("failed to configure Redis client")?;
        let nats = async_nats::connect(&config.nats_url)
            .await
            .context("failed to connect to NATS")?;

        Ok(Self {
            postgres,
            redis,
            nats,
        })
    }

    pub async fn readiness(&self) -> Vec<DependencyProbe> {
        let nats = probe_nats(&self.nats);
        let (postgres, redis) =
            tokio::join!(probe_postgres(&self.postgres), probe_redis(&self.redis));
        vec![postgres, redis, nats]
    }
}

pub fn init_telemetry() {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| {
        EnvFilter::new("sitewatch_api=info,tower_http=info,sqlx=warn,async_nats=warn")
    });

    tracing_subscriber::registry()
        .with(filter)
        .with(tracing_subscriber::fmt::layer().json())
        .init();
}

async fn probe_postgres(pool: &PgPool) -> DependencyProbe {
    let started = Instant::now();
    let result = sqlx::query("SELECT 1").execute(pool).await;
    DependencyProbe {
        name: "postgres",
        healthy: result.is_ok(),
        latency_ms: elapsed_millis(started),
        detail: result.err().map(|error| error.to_string()),
    }
}

async fn probe_redis(client: &redis::Client) -> DependencyProbe {
    let started = Instant::now();
    let result = async {
        let mut connection = client.get_multiplexed_async_connection().await?;
        let pong: String = redis::cmd("PING").query_async(&mut connection).await?;
        Ok::<_, redis::RedisError>(pong)
    }
    .await;
    DependencyProbe {
        name: "redis",
        healthy: result.is_ok(),
        latency_ms: elapsed_millis(started),
        detail: result.err().map(|error| error.to_string()),
    }
}

fn probe_nats(client: &async_nats::Client) -> DependencyProbe {
    let started = Instant::now();
    let state = client.connection_state();
    let healthy = matches!(state, async_nats::connection::State::Connected);
    DependencyProbe {
        name: "nats",
        healthy,
        latency_ms: elapsed_millis(started),
        detail: (!healthy).then(|| format!("connection state: {state:?}")),
    }
}

fn elapsed_millis(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX)
}

fn required_env(name: &str) -> Result<String> {
    env::var(name).with_context(|| format!("required environment variable {name} is missing"))
}

fn env_or(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_owned())
}
