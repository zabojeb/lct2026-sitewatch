FROM rust:1.97-bookworm AS build
WORKDIR /workspace
COPY Cargo.toml Cargo.lock ./
COPY apps apps
COPY crates crates
RUN cargo build --locked --release -p sitewatch-deviations

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10004 --create-home sitewatch
COPY --from=build /workspace/target/release/sitewatch-deviations /usr/local/bin/sitewatch-deviations
USER 10004
EXPOSE 8084
ENTRYPOINT ["sitewatch-deviations"]
