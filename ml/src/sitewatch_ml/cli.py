from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from sitewatch_ml.audit import audit_dataset
from sitewatch_ml.config import PROJECT_ROOT, load_experiment_config, load_pipeline_config
from sitewatch_ml.ingest import ingest_archive
from sitewatch_ml.labeling import create_label_studio_tasks, import_label_studio_export
from sitewatch_ml.prepare import prepare_yolo_dataset
from sitewatch_ml.split import create_split_manifest

app = typer.Typer(
    no_args_is_help=True,
    help="Reproducible SiteWatch dataset and experiment pipeline.",
)
ConfigOption = Annotated[
    Path | None,
    typer.Option("--config", help="Pipeline configuration YAML."),
]


@app.command()
def ingest(
    archive: Annotated[Path | None, typer.Option(help="Organizer ZIP archive.")] = None,
    config: ConfigOption = None,
) -> None:
    """Extract image assets safely and create a content-addressed source manifest."""
    pipeline = load_pipeline_config(config)
    source = archive.resolve() if archive else pipeline.paths.source_archive
    pipeline.paths.annotations.mkdir(parents=True, exist_ok=True)
    manifest = pipeline.paths.manifests / "source-manifest.jsonl"
    records = ingest_archive(source, pipeline.paths.raw_images, manifest)
    typer.echo(f"ingested {len(records)} unique images; manifest={manifest}")


@app.command()
def audit(config: ConfigOption = None) -> None:
    """Validate images and YOLO annotations, duplicates and training readiness."""
    pipeline = load_pipeline_config(config)
    report_path = pipeline.paths.manifests / "quality-report.json"
    report = audit_dataset(
        pipeline.paths.raw_images,
        pipeline.paths.annotations,
        report_path,
        near_duplicate_distance=pipeline.split.near_duplicate_hamming_distance,
    )
    typer.echo(report.model_dump_json(indent=2))


@app.command()
def split(config: ConfigOption = None) -> None:
    """Create a deterministic split while keeping near-duplicate images together."""
    pipeline = load_pipeline_config(config)
    output = pipeline.paths.manifests / "split-manifest.json"
    manifest = create_split_manifest(
        pipeline.paths.raw_images, output, pipeline.split, pipeline.seed
    )
    typer.echo(json.dumps(manifest.counts, ensure_ascii=False))


@app.command("labeling-tasks")
def labeling_tasks(config: ConfigOption = None) -> None:
    """Generate Label Studio import tasks for all organizer images."""
    pipeline = load_pipeline_config(config)
    output = pipeline.paths.manifests / "label-studio-tasks.json"
    tasks = create_label_studio_tasks(pipeline.paths.raw_images, output)
    typer.echo(f"generated {len(tasks)} tasks; output={output}")


@app.command("import-labels")
def import_labels(
    export: Annotated[Path, typer.Option(help="Label Studio JSON export.")],
    config: ConfigOption = None,
) -> None:
    """Validate a Label Studio export and atomically create YOLO annotations."""
    pipeline = load_pipeline_config(config)
    report = import_label_studio_export(
        export.resolve(),
        pipeline.paths.raw_images,
        pipeline.paths.annotations,
        pipeline.paths.manifests / "label-import-report.json",
        pipeline.paths.annotation_export,
    )
    typer.echo(report.model_dump_json(indent=2))


@app.command()
def prepare(config: ConfigOption = None) -> None:
    """Materialize a training-ready YOLO dataset after all quality gates pass."""
    pipeline = load_pipeline_config(config)
    dataset_yaml = prepare_yolo_dataset(
        pipeline.paths.raw_images,
        pipeline.paths.annotations,
        pipeline.paths.manifests / "quality-report.json",
        pipeline.paths.manifests / "split-manifest.json",
        pipeline.paths.prepared_dataset,
    )
    typer.echo(f"dataset prepared: {dataset_yaml}")


@app.command("experiment-audit")
def experiment_audit(config: ConfigOption = None) -> None:
    """Log the immutable dataset quality snapshot as an MLflow experiment run."""
    from sitewatch_ml.experiments import log_dataset_audit

    pipeline = load_pipeline_config(config)
    run_id = log_dataset_audit(pipeline, pipeline.paths.manifests / "quality-report.json")
    typer.echo(f"MLflow run: {run_id}")


@app.command()
def train(
    experiment_config: Annotated[
        Path,
        typer.Option("--experiment-config", "--experiment", help="Experiment YAML."),
    ] = PROJECT_ROOT / "config" / "experiments" / "baseline.yaml",
    config: ConfigOption = None,
) -> None:
    """Train, evaluate, export and register a detector candidate."""
    from sitewatch_ml.experiments import train_detector

    pipeline = load_pipeline_config(config)
    experiment = load_experiment_config(experiment_config)
    dataset_yaml = prepare_yolo_dataset(
        pipeline.paths.raw_images,
        pipeline.paths.annotations,
        pipeline.paths.manifests / "quality-report.json",
        pipeline.paths.manifests / "split-manifest.json",
        pipeline.paths.prepared_dataset,
    )
    manifest = train_detector(pipeline, experiment, dataset_yaml, experiment_config)
    typer.echo(manifest.model_dump_json(indent=2))


@app.command()
def promote(
    run_id: Annotated[str, typer.Option(help="Candidate MLflow run id.")],
    config: ConfigOption = None,
) -> None:
    """Move a registered, gate-passing candidate to the champion alias."""
    from sitewatch_ml.experiments import promote_candidate

    pipeline = load_pipeline_config(config)
    version = promote_candidate(
        pipeline.tracking.uri, pipeline.tracking.registry_model_name, run_id
    )
    typer.echo(f"champion={pipeline.tracking.registry_model_name}@{version}")


if __name__ == "__main__":
    app()
