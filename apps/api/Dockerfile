FROM rust:1.97-bookworm AS build
WORKDIR /workspace

COPY Cargo.toml Cargo.lock ./
COPY apps apps
COPY crates crates
COPY migrations migrations
RUN cargo build --release -p sitewatch-api --bin sitewatch-api --bin migrate

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --create-home sitewatch
COPY --from=build /workspace/target/release/sitewatch-api /usr/local/bin/sitewatch-api
COPY --from=build /workspace/target/release/migrate /usr/local/bin/migrate
USER sitewatch
EXPOSE 8080
ENTRYPOINT ["sitewatch-api"]
