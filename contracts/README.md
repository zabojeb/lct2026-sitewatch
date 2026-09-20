# SiteWatch contracts

This directory is the boundary between the browser, Rust workloads and future ML tooling.

- `openapi.yaml` defines synchronous HTTP calls.
- `asyncapi.yaml` defines durable NATS JetStream messages.
- `schemas/work-stage-import.schema.json` defines normalized schedule imports.
- `examples/` contains executable examples used by tests and demos.

## Compatibility policy

1. HTTP paths live under `/api/v1`. Existing fields remain compatible within v1.
2. Event names and subjects end in `.v1`; incompatible payload changes require a new subject.
3. Every asynchronous message uses a CloudEvents-compatible envelope with `id`, `time`,
   `correlation_id` and optional `causation_id`.
4. Equipment and deviation codes are stable machine values. Russian titles are presentation data.
5. Bounding boxes are normalized to `[0, 1]`, independent of the source image resolution.
6. Timestamps use RFC 3339 UTC values. Project time zones affect display and schedule import only.

Run `make contracts` after changing a contract. This validates OpenAPI, AsyncAPI and the schedule
JSON Schema example, then regenerates the SvelteKit TypeScript types.
