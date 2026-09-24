from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from sitewatch_ml.io import read_json, sha256_file, write_json
from sitewatch_ml.models import (
    ClassifierExperimentConfig,
    DatasetQualityReport,
    EquipmentClass,
    ExperimentConfig,
    ModelManifest,
    PipelineConfig,
)


def _macro_f1(matrix: list[list[float]]) -> float | None:
    """Macro F1 from a square, class-by-class validation confusion matrix."""
    size = len(matrix)
    if not size or any(len(row) != size for row in matrix):
        return None
    scores: list[float] = []
    for index in range(size):
        tp = matrix[index][index]
        denominator = sum(matrix[index]) + sum(row[index] for row in matrix)
        if denominator <= 0:
            return None
        scores.append(2 * tp / denominator)
    return sum(scores) / size


def log_dataset_audit(config: PipelineConfig, report_path: Path) -> str:
    report = DatasetQualityReport.model_validate(read_json(report_path))
    mlflow.set_tracking_uri(config.tracking.uri)
    mlflow.set_experiment(config.tracking.experiment_name)
    with mlflow.start_run(run_name=f"dataset-audit-{report.dataset_fingerprint[:8]}") as run:
        mlflow.set_tags(
            {
                "sitewatch.stage": "dataset_audit",
                "sitewatch.dataset_fingerprint": report.dataset_fingerprint,
                "sitewatch.training_ready": str(report.training_ready).lower(),
                "sitewatch.code_revision": code_revision(),
            }
        )
        mlflow.log_metrics(
            {
                "dataset.image_count": float(report.image_count),
                "dataset.labeled_image_count": float(report.labeled_image_count),
                "dataset.annotation_count": float(report.annotation_count),
                "dataset.invalid_image_count": float(report.invalid_image_count),
                "dataset.invalid_annotation_count": float(report.invalid_annotation_count),
                "dataset.near_duplicate_groups": float(len(report.near_duplicate_groups)),
            }
        )
        mlflow.log_artifact(str(report_path), artifact_path="dataset")
        return run.info.run_id


def train_detector(
    pipeline: PipelineConfig,
    experiment: ExperimentConfig,
    dataset_yaml: Path,
    experiment_config_path: Path,
) -> ModelManifest:
    try:
        from ultralytics import YOLO, settings
    except ImportError as error:
        message = "training dependencies are missing; run `uv sync --extra train`"
        raise RuntimeError(message) from error

    settings.update({"mlflow": False})
    mlflow.set_tracking_uri(pipeline.tracking.uri)
    mlflow.set_experiment(pipeline.tracking.experiment_name)
    quality_report = DatasetQualityReport.model_validate(
        read_json(pipeline.paths.manifests / "quality-report.json")
    )
    run_directory = pipeline.paths.artifacts / "runs" / experiment.name
    run_directory.mkdir(parents=True, exist_ok=True)

    with mlflow.start_run(run_name=experiment.name) as run:
        mlflow.set_tags(
            {
                "sitewatch.stage": "training",
                "sitewatch.lifecycle": "training",
                "sitewatch.dataset_fingerprint": quality_report.dataset_fingerprint,
                "sitewatch.code_revision": code_revision(),
                "sitewatch.framework": "ultralytics",
            }
        )
        mlflow.log_params(_flatten(experiment.model_dump(mode="json")))
        mlflow.log_artifact(str(experiment_config_path), artifact_path="configuration")
        mlflow.log_artifact(
            str(pipeline.paths.manifests / "quality-report.json"), artifact_path="dataset"
        )
        mlflow.log_artifact(
            str(pipeline.paths.manifests / "split-manifest.json"), artifact_path="dataset"
        )

        model = YOLO(experiment.base_model)
        result = model.train(
            data=str(dataset_yaml),
            imgsz=experiment.image_size,
            epochs=experiment.epochs,
            batch=experiment.batch_size,
            patience=experiment.patience,
            workers=experiment.workers,
            device=experiment.device,
            seed=experiment.seed,
            deterministic=experiment.deterministic,
            amp=experiment.amp,
            cache=experiment.cache,
            **experiment.augmentation.model_dump(),
            project=str(run_directory.parent),
            name=run_directory.name,
            exist_ok=True,
        )
        metrics = {
            str(name): float(value)
            for name, value in getattr(result, "results_dict", {}).items()
            if isinstance(value, (int, float))
        }
        mlflow.log_metrics(metrics)

        best_weights = run_directory / "weights" / "best.pt"
        if not best_weights.is_file():
            raise RuntimeError(f"trainer did not produce expected weights: {best_weights}")
        exported = Path(
            YOLO(str(best_weights)).export(
                format=experiment.export.format,
                dynamic=experiment.export.dynamic,
                simplify=experiment.export.simplify,
                imgsz=experiment.image_size,
            )
        )
        champion_map = None
        if not pipeline.tracking.uri.startswith(("file:", "sqlite:")):
            champion_map = _champion_map50_95(pipeline.tracking.registry_model_name)
        gate_passed = _passes_gate(metrics, experiment, champion_map)
        gate_tags: dict[str, str] = {
            "sitewatch.promotion_gate": "passed" if gate_passed else "failed"
        }
        if champion_map is not None:
            mlflow.log_metric("gate.champion_map50_95", champion_map)
            gate_tags["sitewatch.champion_map50_95"] = str(champion_map)
        mlflow.set_tags(gate_tags)
        manifest = ModelManifest(
            class_names=list(EquipmentClass),
            model_name=pipeline.tracking.registry_model_name,
            run_id=run.info.run_id,
            dataset_fingerprint=quality_report.dataset_fingerprint,
            code_revision=code_revision(),
            source_model=experiment.base_model,
            artifact_path=str(exported),
            artifact_sha256=sha256_file(exported),
            metrics=metrics,
            promotion_gate_passed=gate_passed,
        )
        manifest_path = run_directory / "model-manifest.json"
        write_json(manifest_path, manifest)
        mlflow.log_artifact(str(best_weights), artifact_path="model")
        mlflow.log_artifact(str(exported), artifact_path="model")
        mlflow.log_artifact(str(manifest_path), artifact_path="model")
        mlflow.set_tag("sitewatch.lifecycle", "candidate" if gate_passed else "rejected")
        if gate_passed and not pipeline.tracking.uri.startswith("file:"):
            _register_candidate(pipeline.tracking.registry_model_name, run.info.run_id)
        return manifest


def train_classifier(
    pipeline: PipelineConfig,
    experiment: ClassifierExperimentConfig,
    dataset_dir: Path,
    experiment_config_path: Path,
) -> ModelManifest:
    """Train the independent crop classifier and gate on validation top-1 and macro F1."""
    try:
        from ultralytics import YOLO, settings
    except ImportError as error:
        message = "training dependencies are missing; run `uv sync --extra train`"
        raise RuntimeError(message) from error

    settings.update({"mlflow": False})
    mlflow.set_tracking_uri(pipeline.tracking.uri)
    mlflow.set_experiment(pipeline.tracking.experiment_name)
    quality_report = DatasetQualityReport.model_validate(
        read_json(pipeline.paths.manifests / "quality-report.json")
    )
    crop_records = read_json(dataset_dir / "crop-manifest.json")
    class_names = sorted({record["class"] for record in crop_records})
    run_directory = pipeline.paths.artifacts / "runs" / experiment.name
    run_directory.mkdir(parents=True, exist_ok=True)
    model_name = f"{pipeline.tracking.registry_model_name}-classifier"

    with mlflow.start_run(run_name=experiment.name) as run:
        mlflow.set_tags(
            {
                "sitewatch.stage": "classification_training",
                "sitewatch.lifecycle": "training",
                "sitewatch.dataset_fingerprint": quality_report.dataset_fingerprint,
                "sitewatch.code_revision": code_revision(),
                "sitewatch.framework": "ultralytics",
                "sitewatch.task": "classify",
            }
        )
        mlflow.log_params(_flatten(experiment.model_dump(mode="json")))
        mlflow.log_artifact(str(experiment_config_path), artifact_path="configuration")
        mlflow.log_artifact(str(dataset_dir / "crop-manifest.json"), artifact_path="dataset")
        model = YOLO(experiment.base_model)
        model.train(
            data=str(dataset_dir),
            imgsz=experiment.image_size,
            epochs=experiment.epochs,
            batch=experiment.batch_size,
            patience=experiment.patience,
            workers=experiment.workers,
            device=experiment.device,
            seed=experiment.seed,
            deterministic=experiment.deterministic,
            amp=experiment.amp,
            cache=experiment.cache,
            project=str(run_directory.parent),
            name=run_directory.name,
            exist_ok=True,
        )
        best_weights = run_directory / "weights" / "best.pt"
        if not best_weights.is_file():
            raise RuntimeError(f"trainer did not produce expected weights: {best_weights}")
        best = YOLO(str(best_weights))
        validation = best.val(data=str(dataset_dir), split="val")
        metrics = {
            str(name): float(value)
            for name, value in getattr(validation, "results_dict", {}).items()
            if isinstance(value, (int, float))
        }
        matrix = getattr(getattr(validation, "confusion_matrix", None), "matrix", None)
        macro_f1 = _macro_f1(matrix.tolist()) if matrix is not None else None
        if macro_f1 is not None:
            metrics["metrics/macro_f1"] = macro_f1
        mlflow.log_metrics(metrics)
        top1 = metrics.get("metrics/accuracy_top1")
        gate_passed = bool(
            top1 is not None
            and top1 >= experiment.top1_gate_min
            and macro_f1 is not None
            and macro_f1 >= experiment.macro_f1_gate_min
        )
        exported = Path(
            best.export(
                format=experiment.export.format,
                dynamic=experiment.export.dynamic,
                simplify=experiment.export.simplify,
                imgsz=experiment.image_size,
            )
        )
        manifest = ModelManifest(
            task="classify",
            class_names=class_names,
            model_name=model_name,
            run_id=run.info.run_id,
            dataset_fingerprint=quality_report.dataset_fingerprint,
            code_revision=code_revision(),
            source_model=experiment.base_model,
            artifact_path=str(exported),
            artifact_sha256=sha256_file(exported),
            metrics=metrics,
            promotion_gate_passed=gate_passed,
        )
        manifest_path = run_directory / "model-manifest.json"
        write_json(manifest_path, manifest)
        mlflow.log_artifact(str(best_weights), artifact_path="model")
        mlflow.log_artifact(str(exported), artifact_path="model")
        mlflow.log_artifact(str(manifest_path), artifact_path="model")
        mlflow.set_tag("sitewatch.lifecycle", "candidate" if gate_passed else "rejected")
        if gate_passed and not pipeline.tracking.uri.startswith("file:"):
            _register_candidate(model_name, run.info.run_id)
        return manifest


def promote_candidate(tracking_uri: str, model_name: str, run_id: str) -> str:
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    matching = [version for version in client.search_model_versions(f"run_id = '{run_id}'")]
    if len(matching) != 1 or matching[0].name != model_name:
        raise ValueError(f"expected exactly one registered version for run {run_id}")
    run = client.get_run(run_id)
    if run.data.tags.get("sitewatch.lifecycle") != "candidate":
        raise ValueError(f"run {run_id} did not pass the candidate promotion gate")
    version = str(matching[0].version)
    try:
        previous = client.get_model_version_by_alias(model_name, "champion")
    except MlflowException as error:
        if error.error_code != "RESOURCE_DOES_NOT_EXIST":
            raise
    else:
        if str(previous.version) != version:
            client.set_model_version_tag(
                model_name,
                str(previous.version),
                "sitewatch.lifecycle",
                "retired",
            )
    client.set_registered_model_alias(model_name, "champion", version)
    client.set_model_version_tag(model_name, version, "sitewatch.lifecycle", "champion")
    client.set_tag(run_id, "sitewatch.lifecycle", "champion")
    try:
        candidate = client.get_model_version_by_alias(model_name, "candidate")
        if str(candidate.version) == version:
            client.delete_registered_model_alias(model_name, "candidate")
    except MlflowException as error:
        if error.error_code != "RESOURCE_DOES_NOT_EXIST":
            raise
    return version


def code_revision() -> str:
    configured = os.getenv("SITEWATCH_CODE_REVISION")
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "uncommitted"
    return result.stdout.strip() if result.returncode == 0 else "uncommitted"


def _register_candidate(model_name: str, run_id: str) -> None:
    client = MlflowClient()
    try:
        client.create_registered_model(model_name)
    except MlflowException as error:
        if "already exists" not in str(error).lower():
            raise
    version = client.create_model_version(
        name=model_name,
        source=f"runs:/{run_id}/model",
        run_id=run_id,
        tags={"sitewatch.lifecycle": "candidate"},
    )
    client.set_registered_model_alias(model_name, "candidate", str(version.version))


def _champion_map50_95(model_name: str) -> float | None:
    client = MlflowClient()
    try:
        champion = client.get_model_version_by_alias(model_name, "champion")
    except MlflowException as error:
        if error.error_code == "RESOURCE_DOES_NOT_EXIST":
            return None
        raise
    if champion.run_id is None:
        return None
    return _metric_value(client.get_run(champion.run_id).data.metrics, "map50_95")


def _passes_gate(
    metrics: dict[str, float],
    experiment: ExperimentConfig,
    champion_map50_95: float | None = None,
) -> bool:
    map50_95 = _metric_value(metrics, "map50_95")
    precision = _metric_value(metrics, "precision")
    recall = _metric_value(metrics, "recall")
    absolute_gate = (
        map50_95 >= experiment.promotion_gate.map50_95_min
        and precision >= experiment.promotion_gate.precision_min
        and recall >= experiment.promotion_gate.recall_min
    )
    regression_gate = champion_map50_95 is None or map50_95 >= (
        champion_map50_95 - experiment.promotion_gate.max_regression_from_champion
    )
    return absolute_gate and regression_gate


def _metric_value(metrics: dict[str, float], name: str) -> float:
    aliases = {
        "map50_95": ("metrics/mAP50-95(B)", "metrics/mAP50-95"),
        "precision": ("metrics/precision(B)", "metrics/precision"),
        "recall": ("metrics/recall(B)", "metrics/recall"),
    }
    return next((metrics[key] for key in aliases[name] if key in metrics), 0.0)


def _flatten(payload: dict[str, Any], prefix: str = "") -> dict[str, str | int | float | bool]:
    flattened: dict[str, str | int | float | bool] = {}
    for key, value in payload.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten(value, name))
        elif isinstance(value, (str, int, float, bool)):
            flattened[name] = value
        else:
            flattened[name] = json.dumps(value, ensure_ascii=False)
    return flattened
