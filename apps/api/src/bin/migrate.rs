use std::env;

use anyhow::{Context, Result};
use sqlx::postgres::PgPoolOptions;

#[tokio::main]
async fn main() -> Result<()> {
    let database_url = env::var("DATABASE_URL")
        .context("required environment variable DATABASE_URL is missing")?;
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(&database_url)
        .await?;
    sqlx::migrate!("../../migrations").run(&pool).await?;
    Ok(())
}
