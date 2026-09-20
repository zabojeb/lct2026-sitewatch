# ADR 0003: Version HTTP and event contracts explicitly

- Status: accepted
- Date: 2026-09-19

## Decision

OpenAPI 3.1, AsyncAPI and JSON Schema are reviewed artifacts in Git. SvelteKit types are generated
from OpenAPI. Rust DTOs mirror the same boundary and are not database models.

HTTP resources live below `/api/v1`. Event subjects end in `.v1`. Additive fields are allowed within
a version. Removing a field, changing its meaning or narrowing an accepted value requires a new
version.

Every command supports idempotency. Every event carries its own id, correlation id and causation id.

## Consequences

- Frontend and backend can work independently without guessing payloads.
- Saved demo fixtures remain replayable.
- Contract drift must fail CI rather than appear during integration.

