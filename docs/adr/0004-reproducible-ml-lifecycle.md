# ADR 0004: Treat datasets, experiments and model promotion as versioned assets

- Status: accepted
- Date: 2026-09-19

## Context

The organizer archive contains images but no bounding-box annotations. A detector trained on invented
labels would make the demo irreproducible and destroy the evidentiary value of detections. Dataset
bytes are also too large and sensitive for Git.

## Decision

- DVC versions dataset artifacts in private S3-compatible storage; Git stores pipeline definitions
  and `dvc.lock` only.
- Label Studio is the human annotation boundary. Its JSON export is validated and converted
  atomically into the canonical YOLO representation.
- Dagster exposes the lineage and executes asset jobs. DVC remains the reproducibility mechanism,
  so orchestration can be replaced without changing dataset identity.
- MLflow stores runs and model aliases in PostgreSQL and artifacts in S3/MinIO.
- Every run records the dataset SHA-256 fingerprint, code revision, experiment configuration,
  metrics and exported-model checksum.
- A model may become `candidate` only after configured metric gates pass. Moving `candidate` to
  `champion` is an explicit command and therefore an auditable release decision.
- Training outputs ONNX for the Rust inference boundary. Training framework objects are never the
  serving contract.

## Consequences

- An unlabeled or partially labeled dataset fails closed before GPU time is consumed.
- Near-duplicate images cannot leak between train, validation and test splits.
- A production observation can be traced back to one model version, experiment and dataset.
- The team must decide the detector framework license and target GPU before the first full training
  run; the data and tracking layers do not depend on that choice.
