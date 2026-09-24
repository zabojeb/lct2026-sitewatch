//! Publish committed outbox rows to `JetStream`. Replays use the same NATS message id.

use std::time::Duration;

use async_nats::jetstream::{Context, message::PublishMessage};
use sqlx::{PgPool, Row};
use tokio::time::{sleep, timeout};
use uuid::Uuid;

pub async fn run(pool: PgPool, jetstream: Context) {
    loop {
        match publish_one(&pool, &jetstream).await {
            Ok(true) => {}
            Ok(false) => sleep(Duration::from_millis(500)).await,
            Err(error) => {
                tracing::warn!(%error, "outbox publish failed; will retry");
                sleep(Duration::from_secs(2)).await;
            }
        }
    }
}

async fn publish_one(pool: &PgPool, jetstream: &Context) -> anyhow::Result<bool> {
    let mut tx = pool.begin().await?;
    let row = sqlx::query(
        "SELECT id, subject, payload FROM outbox_events WHERE published_at IS NULL \
         ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED",
    )
    .fetch_optional(&mut *tx)
    .await?;
    let Some(row) = row else {
        tx.commit().await?;
        return Ok(false);
    };
    let id: Uuid = row.try_get("id")?;
    let subject: String = row.try_get("subject")?;
    let payload: serde_json::Value = row.try_get("payload")?;
    let message = PublishMessage::build()
        .payload(serde_json::to_vec(&payload)?.into())
        .message_id(id.to_string());
    let Ok(Ok(ack)) = timeout(
        Duration::from_secs(5),
        jetstream.send_publish(subject, message),
    )
    .await
    else {
        record_failure(&mut tx, id, "jetstream_publish_failed").await?;
        tx.commit().await?;
        anyhow::bail!("JetStream publish failed")
    };
    if !matches!(timeout(Duration::from_secs(5), ack).await, Ok(Ok(_))) {
        record_failure(&mut tx, id, "jetstream_ack_failed").await?;
        tx.commit().await?;
        anyhow::bail!("JetStream publish acknowledgement failed")
    }
    sqlx::query("UPDATE outbox_events SET published_at = now(), attempts = attempts + 1, last_error = NULL WHERE id = $1")
        .bind(id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(true)
}

async fn record_failure(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    id: Uuid,
    reason_code: &'static str,
) -> anyhow::Result<()> {
    sqlx::query("UPDATE outbox_events SET attempts = attempts + 1, last_error = $2 WHERE id = $1")
        .bind(id)
        .bind(reason_code)
        .execute(&mut **tx)
        .await?;
    Ok(())
}
