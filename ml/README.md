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
uv run sitewatch-ml train --config config/experiments/baseline.yaml
```

See [`../docs/mlops.md`](../docs/mlops.md) for the complete local and Kubernetes workflow.
