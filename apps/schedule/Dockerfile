FROM rust:1.97-bookworm AS build
WORKDIR /workspace
COPY Cargo.toml Cargo.lock ./
COPY apps apps
COPY crates crates
COPY migrations migrations
RUN cargo build --locked --release -p sitewatch-schedule --bin sitewatch-schedule --bin migrate --bin provision_nats

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10002 --create-home sitewatch
COPY --from=build /workspace/target/release/sitewatch-schedule /usr/local/bin/sitewatch-schedule
COPY --from=build /workspace/target/release/migrate /usr/local/bin/schedule-migrate
COPY --from=build /workspace/target/release/provision_nats /usr/local/bin/schedule-provision-nats
USER 10002
EXPOSE 8082
ENTRYPOINT ["sitewatch-schedule"]
