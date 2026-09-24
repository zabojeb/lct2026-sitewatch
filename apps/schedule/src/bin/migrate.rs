use anyhow::{Context, Result};
use sqlx::postgres::PgPoolOptions;

#[tokio::main]
async fn main() -> Result<()> {
    let database_url = std::env::var("SCHEDULE_MIGRATION_DATABASE_URL")
        .context("SCHEDULE_MIGRATION_DATABASE_URL is required")?;
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(&database_url)
        .await?;
    sqlx::migrate!("../../migrations/schedule")
        .run(&pool)
        .await?;
    // Runtime can only perform the operations the service needs. It cannot alter
    // migration history, delete immutable revisions or rewrite evidence rules.
    sqlx::query(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sitewatch_schedule') THEN \
         REVOKE ALL ON schedule_revisions, work_stages, equipment_rules, active_schedule_revisions, outbox_events, _sqlx_migrations FROM sitewatch_schedule; \
         GRANT SELECT, INSERT ON schedule_revisions, work_stages, equipment_rules TO sitewatch_schedule; \
         GRANT UPDATE (activation_version) ON schedule_revisions TO sitewatch_schedule; \
         GRANT SELECT, INSERT, UPDATE ON active_schedule_revisions, outbox_events TO sitewatch_schedule; \
         END IF; END $$",
    )
    .execute(&pool)
    .await?;
    println!("schedule migrations applied");
    Ok(())
}
