# Live schedule service

`apps/schedule` is the first production-path microservice. It does not use the ML model. It owns
`sitewatch_schedule` in the shared PostgreSQL cluster and never queries another service's tables.
The old `apps/api` and browser-local `/app` demo remain separate; this service is **not** a browser
fallback or a public endpoint.

## Local start

1. Start PostgreSQL and NATS with `make infra-up`.
2. Copy `.env.example` to `.env`. Generate distinct random values for
   `SCHEDULE_DB_PASSWORD`, `SCHEDULE_MIGRATION_DB_PASSWORD` and `SITEWATCH_INTERNAL_TOKEN`
   (at least 32 bytes for the token). Set both schedule PostgreSQL URLs from those passwords,
   using host `postgres` for Docker Compose. URL-encode reserved characters. Never commit `.env`.
3. Run `docker compose -f deploy/compose.yaml --profile live up -d --build schedule`.

The dependency jobs create the database and separate roles, apply the schedule-owned migrations,
and ensure the `SITEWATCH_EVENTS` JetStream stream exists. PostgreSQL provisioning is idempotent
for an already initialized local volume. The runtime role cannot change migration history or
delete immutable revisions. Local port 8082 is bound to loopback only.

To call the private API from a trusted local shell, send `Authorization: Bearer
<SITEWATCH_INTERNAL_TOKEN>`. Never place that token in `PUBLIC_*` variables or browser code.
`POST /api/v1/projects/{projectId}/stages:import` requires a UUID `Idempotency-Key` and a body
following `WorkStageImport` in OpenAPI. It returns 201 for a new immutable revision, 200 for an
identical replay and 409 if the same key is reused with different content. Read the active plan
with `GET /api/v1/projects/{projectId}/stages`, or a specific revision with
`GET /api/v1/projects/{projectId}/stages/revisions/{revisionId}`.

An import transaction writes the revision, stages, sourced equipment rules, active pointer and
outbox row. The publisher sends `lct.schedule.revision_activated.v1` after commit and records the
JetStream ack. Publish retries reuse the event UUID as `Nats-Msg-Id`. Consumers must still dedupe
by event UUID and compare `activation_version`: delivery is at least once and may be out of order.
The event contains identifiers and the monotonic version, not the whole plan; a consumer can fetch
the immutable revision over internal HTTP. The service does not assert a violation from a rule or
detector result by itself.

## Kubernetes

The base Kustomize bundle contains a private ClusterIP schedule Deployment/Service, dedicated
ConfigMap, Secret and ServiceAccount. It does **not** add a public Ingress route. Replace all
`REPLACE_ME` secret values through your secret-management system, provision the PostgreSQL roles,
then run `deploy/k8s/jobs/schedule-migrate-v1.yaml` and
`deploy/k8s/jobs/schedule-provision-nats-v1.yaml` to completion before rolling out the Deployment.
These one-time Jobs deliberately are not part of the long-running Kustomize base. TLS gateway,
namespace network policies and actual managed PostgreSQL/NATS endpoints still require the target
cluster configuration.

## Verified locally

- Both migrations applied on a clean PostGIS database; the disposable verification database was removed.
- Runtime role had read/insert for revisions, update only for activation version, no delete on
  revisions and no write to `_sqlx_migrations`.
- Real HTTP requests returned 201, replay 200, changed-body replay 409 and missing token 401.
  Two successive revisions had versions 1 and 2; active read returned 2, immutable read returned 1.
- Both corresponding outbox rows were acknowledged by JetStream.

The model-independent product path still needs identity/OIDC, the gateway/BFF, projects/zones,
real observation storage and manual entry, deviations/reviews, notifications and UI integration.
Those are not claimed as finished here.
