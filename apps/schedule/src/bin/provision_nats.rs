use anyhow::{Context, Result};
use async_nats::jetstream::{self, stream::Config};

#[tokio::main]
async fn main() -> Result<()> {
    let url = std::env::var("NATS_URL").context("NATS_URL is required")?;
    let client = async_nats::connect(url).await?;
    let jetstream = jetstream::new(client);
    jetstream
        .get_or_create_stream(Config {
            name: "SITEWATCH_EVENTS".into(),
            subjects: vec!["lct.>".into()],
            ..Config::default()
        })
        .await?;
    println!("SITEWATCH_EVENTS stream ready");
    Ok(())
}
