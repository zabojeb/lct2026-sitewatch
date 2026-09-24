# ADR 0005: Independently deployed backend services on Kubernetes

- Status: accepted; implementation in progress (schedule service implemented)
- Date: 2026-09-20
- Supersedes: ADR 0001
- Decision owner: user, confirmed in the architecture discussion

## Decision

The backend is a set of independently deployable Rust services. Kubernetes is the deployment target.
One physical PostgreSQL cluster hosts a separate database and separate roles for each service.
Services cannot query another service's tables. NATS JetStream carries versioned domain events.
The Python training/experimentation platform remains a separate MLOps workload; inference is an
independently deployable runtime, not code executed in a web request.

This ADR defines the target architecture. `apps/schedule` is the first independently deployed
service with its own database, runtime/migration roles, immutable revisions and transactional
outbox. The existing `apps/api` process and consolidated migration are a legacy bootstrap, not an
implementation of the other service boundaries. Do not grow that process into a business monolith.
The UI currently runs explicitly synthetic browser-local scenarios.

## Ownership

| Service | Owns | Database | Communication |
| --- | --- | --- | --- |
| identity | tenants, membership, roles, authorization policy | `sitewatch_identity` | OIDC integration, membership events |
| projects | projects, zones, camera metadata and secret references | `sitewatch_projects` | project/camera APIs, configuration events |
| schedule | plan imports, stages, equipment requirements, revisions | `sitewatch_schedule` | plan APIs, immutable schedule events |
| observations | upload slots, immutable asset refs, observations and their lifecycle | `sitewatch_observations` | presigned uploads, observation APIs/events |
| inference | jobs, model versions, detections, execution metadata | `sitewatch_inference` | consumes accepted observations, emits analyzed events |
| deviations | temporal rule evaluations, evidence snapshots, review decisions | `sitewatch_deviations` | consumes detections/schedule, serves deviations/reviews |
| notifications | delivery preferences, attempts, deduplication and audit | `sitewatch_notifications` | consumes deviation events; adapters isolated by channel |

An edge gateway/BFF owns no business database and performs routing/composition, authentication
validation, request budgets and correlation propagation. Shared Rust crates may hold pure domain
types and wire contracts, never shared repositories or service-specific persistence models.
Use an established OIDC provider; do not implement password cryptography in the identity service.
Provider selection and external notification channels are separate decisions, not silently assumed.

## PostgreSQL isolation

- Separate migration owner and runtime role per database. Runtime roles have no superuser,
  `CREATEDB`, `CREATEROLE`, replication or cross-service role membership.
- Revoke default `CONNECT`/`TEMP` privileges from `PUBLIC`; grant only the owning service.
  Do not enable `dblink` or foreign-data wrappers to bypass ownership.
- Store credentials in per-service Secrets, not one shared `DATABASE_URL` for all deployments.
  Application containers never receive PostgreSQL operator credentials.
- Each service owns migrations and outbox in its own database. There are no cross-database foreign
  keys, joins or distributed transactions. References are IDs; consumers own projections.
- PostGIS is required for the projects database. Other databases use it only with a concrete need.
- Partition connection-pool budgets across replicas; one physical cluster is shared capacity and a
  shared failure domain. Test backups and point-in-time recovery before production.

## Event flow and consistency

1. Observations commits metadata and `observation.accepted.v1` to its local outbox.
2. Its publisher delivers the event to JetStream with a stable event ID.
3. Inference consumes it, writes detections/model provenance and an analyzed-event outbox record in
   its own transaction. It accesses object storage under a scoped workload identity.
4. Deviations consumes detection and versioned schedule/zone events into owned projections. It
   evaluates only when prerequisites exist; missing or stale context yields insufficient evidence.
5. A deviation retains rule revision, expected state, observed state and immutable evidence refs.
   Review actions modify workflow state, not historical evidence or detector output.
6. Notifications records an idempotent delivery intent before calling a configured provider.

Every consumer has an inbox unique on `(consumer, event_id)` and acknowledges only after commit.
Retries are bounded; poison messages go to a dead-letter subject. Outbox replay and duplicate
delivery are expected. No claim of exactly-once delivery is made. Ordering uses aggregate revision,
not wall-clock arrival. A delayed event must not overwrite a newer projection.

PostgreSQL remains authoritative; Redis only stores disposable caches/windows. Rule windows must be
reconstructable from persisted observations. S3 holds image bytes and model artifacts. No credentials,
RTSP URLs or image bytes are placed in events or logs. Exported evidence must be tenant-scoped.

## Kubernetes deployment contract

- One image and Deployment per service, with independent version, release and rollback.
- One ServiceAccount, Secret, ConfigMap and NetworkPolicy per service. Default-deny ingress/egress;
  explicitly allow DNS, gateway/internal APIs and only required PostgreSQL, NATS, S3/Redis endpoints.
- ClusterIP for internal HTTP; the only public application entry is the TLS gateway and SvelteKit.
  MLflow, Dagster, annotation tools and NATS monitoring are not public unauthenticated routes.
- Liveness checks the process; readiness checks the dependencies the service requires. Consumers
  stop accepting work, finish or release leases, and drain NATS on SIGTERM.
- Resource requests/limits, non-root, read-only root filesystem, dropped capabilities and no default
  service-account token. Explicit temporary volumes only where runtime requires them.
- HTTP replicas use latency/CPU-based HPA; workers use queue-depth/age metrics. GPU inference runs in
  its own node pool with device requests. KEDA, ingress/Gateway implementation and GitOps controller
  are deployment choices to confirm against the actual cluster, not assumed installed.
- Migration Jobs run once per service version before rollout, under the migration role. A Deployment
  init-container must not race multiple schema changes. Use expand/contract migrations for rollback.
- Distributed traces carry request/event correlation IDs. Track queue age, inference failures,
  insufficient-evidence rate, outbox lag and notification failures separately.

## Implementation sequence and acceptance gates

1. Establish service crates, health probes, image builds and per-service deployment manifests.
2. Provision isolated databases/roles and migrate owned tables; verify cross-service access denied.
3. Implement projects, schedule and observation APIs with tenant authorization and idempotency.
4. Implement outbox/inbox, inference and deviation path; test duplicate and out-of-order delivery.
5. Connect the SvelteKit API adapter. Keep `/app` demo mode explicit until this integration passes.
6. Add notification adapters after provider choice; never send real messages during demo tests.
7. Validate clean database migrations, contracts, Rust checks, Kubernetes schemas and end-to-end tests
   in a disposable namespace. Deploy to a user's actual cluster only after resolving its context.

Merely creating seven containers around one shared database schema does not satisfy this ADR.
