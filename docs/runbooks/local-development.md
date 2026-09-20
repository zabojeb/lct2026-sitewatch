# Local development runbook

## Start infrastructure

```bash
cp .env.example .env
make bootstrap
make infra-up
```

The infrastructure command starts PostgreSQL/PostGIS, Redis, NATS JetStream and MinIO, then creates
the private `sitewatch-evidence` bucket.

## Run API locally

```bash
set -a
source .env
set +a
cargo run -p sitewatch-api --bin migrate
cargo run -p sitewatch-api --bin sitewatch-api
```

Validate probes:

```bash
curl -fsS http://localhost:8080/health/live
curl -fsS http://localhost:8080/health/ready
```

## Run web locally

```bash
pnpm dev
```

## Reset local state

`docker compose -f deploy/compose.yaml down` preserves volumes. To remove local database, queue and
object data as an explicit destructive action, run:

```bash
docker compose -f deploy/compose.yaml down --volumes
```

Never run this against shared infrastructure.

