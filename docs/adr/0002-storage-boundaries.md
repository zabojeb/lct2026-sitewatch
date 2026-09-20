# ADR 0002: PostgreSQL, Redis, S3 and NATS have distinct responsibilities

- Status: accepted
- Date: 2026-09-19

## Decision

Use PostgreSQL/PostGIS as the only system of record, Redis for disposable operational state,
S3-compatible storage for binary assets and NATS JetStream for durable event transport.

PostGIS is included because camera locations, coverage polygons and construction zones are spatial
facts. MinIO provides the same S3 contract locally. Redis is never required to reconstruct an audit.

## Rejected alternatives

- PostgreSQL blobs: expensive backups and poor image delivery.
- Redis Streams as the sole bus: usable for an MVP, but couples caching and durable messaging failure
  domains.
- Kafka/Redpanda: strong platform, unnecessary operational weight for the initial camera volume.

