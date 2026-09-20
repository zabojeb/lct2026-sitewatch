# Repository guidance

## Scope

SiteWatch is an explainable construction-site monitoring platform. Preserve the distinction between
object detection, schedule interpretation and deviation rules. A detector result is evidence, not a
business violation by itself.

## Required checks

Before completing code changes, run the checks relevant to the touched area:

- Rust: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`,
  `cargo test --workspace`.
- Web: `pnpm check` and `pnpm build`.
- Contracts: `pnpm contracts:lint` and `pnpm contracts:generate`.
- Kubernetes: `make k8s-validate`.
- Database changes: apply all migrations against a clean PostGIS database.

## Architecture invariants

- Backend target: independently deployed microservices on Kubernetes (ADR 0005 supersedes ADR 0001).
- One PostgreSQL cluster, separate database and roles per service. No cross-service table access.
- Do not add new business handlers to the legacy `apps/api` bootstrap; implement in owning services.
- Service-to-service events use NATS JetStream; keep the MLOps platform separate from serving.
- Keep pure business types and invariants in `crates/domain`.
- Keep wire DTOs in `crates/contracts`; do not expose database rows directly.
- PostgreSQL is the system of record. Redis may cache or aggregate disposable windows only.
- Store image bytes in S3-compatible storage; PostgreSQL stores metadata and immutable references.
- Use the outbox table for events created in the same transaction as domain state.
- Consumers must deduplicate by event id and be safe under at-least-once delivery.
- Every deviation must retain the rule, expected state, observed state and evidence used to create it.
- Never classify an unobservable stage as compliant or violating. Return insufficient evidence.

## Contract changes

- Keep `contracts/openapi.yaml`, `contracts/asyncapi.yaml`, Rust DTOs and generated frontend types in
  sync.
- Add fields compatibly within v1. Rename/remove only in a new API or event version.
- Keep timestamps in UTC and bounding boxes normalized to `[0, 1]`.
- Stable enum codes are English snake_case; localised labels belong to presentation metadata.

## Data and secrets

- Do not commit source datasets, model weights, generated evidence or credentials.
- Never place camera credentials or RTSP URLs in ordinary tables, events or logs. Store secret
  references instead.
- Treat source images and annotated evidence as sensitive operational data.
