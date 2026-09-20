FROM postgres:17.6-bookworm

# The upstream postgis/postgis images are amd64-only. Building from the official
# multi-architecture PostgreSQL image keeps local development native on both
# Apple Silicon and x86_64 while still installing PostGIS from the PGDG repo.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        postgresql-17-postgis-3 \
        postgresql-17-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
