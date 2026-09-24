# SiteWatch ML platform

Reproducible data preparation, experiment tracking and detector training. The default environment
contains only the lightweight control plane. Heavy training and orchestration dependencies are
explicit extras.

```bash
cd ml
uv sync --group dev --extra data
uv run sitewatch-ml ingest --archive ../7.ДГП_датасеты.zip
uv run sitewatch-ml audit
uv run sitewatch-ml split
uv run sitewatch-ml labeling-tasks
uv run pytest
```

Import the completed Label Studio export without leaving stale labels behind:

```bash
uv run sitewatch-ml import-labels --export /path/to/project-export.json
uv run sitewatch-ml audit
uv run sitewatch-ml split
uv run sitewatch-ml prepare
```

Training becomes available only after YOLO annotations exist:

```bash
uv sync --group dev --extra train
uv run sitewatch-ml train --experiment-config config/experiments/baseline.yaml
uv run sitewatch-ml train-classifier --experiment-config config/experiments/classifier-baseline.yaml
```

See [`../docs/mlops.md`](../docs/mlops.md) for the complete local and Kubernetes workflow.
The classifier command builds split-safe crops from admitted detection labels and applies
machine-only augmentations to train crops. Detector scene augmentations are configured
separately. Weather/season background synthesis and temporal violation scenarios are not
currently materialized; their prerequisites and evaluation gates are recorded in
[`../docs/schedule-and-evidence-requirements.md`](../docs/schedule-and-evidence-requirements.md).

## External source audit

Source versions, public download URLs and admission restrictions are recorded in
`config/external-sources.json`. Raw archives live at
`../data/ml/external/<source-id>/source.zip` and must never be committed to Git.
Four source archives were acquired; the listed Roboflow project has no published version.

Run from the repository root after installing the locked ML environment:

```bash
ml/.venv/bin/python -m sitewatch_ml.external_data \
  --organizer data/ml/raw/organizer \
  --summary-output docs/external-data-audit.json
```

The auditor reads ZIP members without extracting or modifying them, fully decodes images,
validates source-taxonomy YOLO or Pascal VOC boxes, checks EXIF metadata, hashes files and
finds byte duplicates plus equal-dHash candidates. Detailed image records remain local;
the versioned report contains aggregate statistics only. `--source <id>` selects one source;
`--reuse` verifies archive, auditor and source-configuration hashes before reusing an audit.
It is not an exhaustive near-duplicate detector or semantic annotation review.

No external archive is automatically mixed into the organizer pipeline. The existing annotation
importer expects the SiteWatch taxonomy, not arbitrary source IDs. Preserve raw data and review
license, mapping, orientation, annotation completeness and scene leakage before conversion.
See [`../docs/analysis-and-evaluation-plan.md`](../docs/analysis-and-evaluation-plan.md).
