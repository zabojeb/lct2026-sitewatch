import dagster as dg

from sitewatch_ml.audit import audit_dataset
from sitewatch_ml.config import load_pipeline_config
from sitewatch_ml.experiments import log_dataset_audit
from sitewatch_ml.ingest import ingest_archive
from sitewatch_ml.io import read_json
from sitewatch_ml.labeling import create_label_studio_tasks
from sitewatch_ml.models import DatasetQualityReport
from sitewatch_ml.split import create_split_manifest


@dg.asset(group_name="dataset", compute_kind="python")
def source_manifest(context: dg.AssetExecutionContext) -> str:
    config = load_pipeline_config()
    config.paths.annotations.mkdir(parents=True, exist_ok=True)
    output = config.paths.manifests / "source-manifest.jsonl"
    records = ingest_archive(config.paths.source_archive, config.paths.raw_images, output)
    context.add_output_metadata(
        {
            "image_count": len(records),
            "manifest": dg.MetadataValue.path(str(output)),
        }
    )
    return str(output)


@dg.asset(group_name="dataset", compute_kind="Pillow", deps=[source_manifest])
def quality_report(context: dg.AssetExecutionContext) -> str:
    config = load_pipeline_config()
    output = config.paths.manifests / "quality-report.json"
    report = audit_dataset(
        config.paths.raw_images,
        config.paths.annotations,
        output,
        near_duplicate_distance=config.split.near_duplicate_hamming_distance,
    )
    context.add_output_metadata(
        {
            "dataset_fingerprint": report.dataset_fingerprint,
            "image_count": report.image_count,
            "annotation_count": report.annotation_count,
            "training_ready": report.training_ready,
            "report": dg.MetadataValue.path(str(output)),
        }
    )
    return str(output)


@dg.asset_check(asset=quality_report, blocking=False)
def annotation_coverage() -> dg.AssetCheckResult:
    config = load_pipeline_config()
    report = DatasetQualityReport.model_validate(
        read_json(config.paths.manifests / "quality-report.json")
    )
    return dg.AssetCheckResult(
        passed=report.training_ready,
        severity=dg.AssetCheckSeverity.WARN,
        metadata={"blockers": report.blockers},
        description="Training is allowed only after every source image has valid annotations.",
    )


@dg.asset(group_name="dataset", compute_kind="python", deps=[quality_report])
def split_manifest(context: dg.AssetExecutionContext) -> str:
    config = load_pipeline_config()
    output = config.paths.manifests / "split-manifest.json"
    manifest = create_split_manifest(config.paths.raw_images, output, config.split, config.seed)
    context.add_output_metadata({**manifest.counts, "manifest": dg.MetadataValue.path(str(output))})
    return str(output)


@dg.asset(group_name="labeling", compute_kind="Label Studio", deps=[source_manifest])
def label_studio_tasks(context: dg.AssetExecutionContext) -> str:
    config = load_pipeline_config()
    output = config.paths.manifests / "label-studio-tasks.json"
    tasks = create_label_studio_tasks(config.paths.raw_images, output)
    context.add_output_metadata(
        {"task_count": len(tasks), "tasks": dg.MetadataValue.path(str(output))}
    )
    return str(output)


@dg.asset(group_name="experiments", compute_kind="MLflow", deps=[quality_report])
def dataset_audit_run(context: dg.AssetExecutionContext) -> str:
    config = load_pipeline_config()
    run_id = log_dataset_audit(config, config.paths.manifests / "quality-report.json")
    context.add_output_metadata({"mlflow_run_id": run_id})
    return run_id


prepare_dataset_job = dg.define_asset_job(
    "prepare_dataset",
    selection=dg.AssetSelection.assets(
        source_manifest,
        quality_report,
        split_manifest,
        label_studio_tasks,
        dataset_audit_run,
    ),
)

defs = dg.Definitions(
    assets=[
        source_manifest,
        quality_report,
        split_manifest,
        label_studio_tasks,
        dataset_audit_run,
    ],
    asset_checks=[annotation_coverage],
    jobs=[prepare_dataset_job],
)
