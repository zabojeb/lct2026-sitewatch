# ADR 0001: Modular core with event-driven processors

- Status: superseded by ADR 0005 (2026-09-20)
- Date: 2026-09-19

## Context

Image inference and temporal rule evaluation scale differently from CRUD and dashboard traffic. A
single synchronous API would make request latency depend on model execution. Splitting every domain
module into a service would slow a hackathon team and create operational work without product value.

## Decision

Keep API and business modules in one Rust workspace. Run inference and rule evaluation as asynchronous
processors behind versioned NATS JetStream contracts. They may share one processor binary during the
MVP and split only when scaling evidence justifies it.

## Consequences

- The first end-to-end path remains simple to debug.
- HTTP latency does not include inference time.
- Processor replicas can scale by queue lag and hardware class.
- Event compatibility and idempotency become mandatory engineering concerns.
