from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EquipmentClass(StrEnum):
    DUMP_TRUCK = "dump_truck"
    EXCAVATOR = "excavator"
    ROAD_ROLLER = "road_roller"
    LOADER_CRANE = "loader_crane"
    CONCRETE_MIXER = "concrete_mixer"
    BULLDOZER = "bulldozer"
    TRUCK = "truck"
    MOBILE_CRANE = "mobile_crane"
    TOWER_CRANE = "tower_crane"
    PILING_RIG = "piling_rig"
    CONCRETE_PUMP = "concrete_pump"
    BUCKET_LOADER = "bucket_loader"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectPaths(StrictModel):
    source_archive: Path
    raw_images: Path
    annotations: Path
    annotation_export: Path
    manifests: Path
    prepared_dataset: Path
    artifacts: Path


class TrackingConfig(StrictModel):
    uri: str
    experiment_name: str
    registry_model_name: str


class SplitConfig(StrictModel):
    train: float = Field(gt=0, lt=1)
    validation: float = Field(gt=0, lt=1)
    test: float = Field(gt=0, lt=1)
    near_duplicate_hamming_distance: int = Field(default=4, ge=0, le=16)

    @model_validator(mode="after")
    def ratios_sum_to_one(self) -> SplitConfig:
        if abs(self.train + self.validation + self.test - 1.0) > 1e-9:
            raise ValueError("split ratios must sum to 1")
        return self


class PipelineConfig(StrictModel):
    project_name: str
    seed: int
    paths: ProjectPaths
    tracking: TrackingConfig
    split: SplitConfig


class AssetRecord(StrictModel):
    asset_id: str
    relative_path: str
    source_member: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    color_mode: str
    annotation_status: str = "unlabeled"


class BoundingBox(StrictModel):
    center_x: float = Field(ge=0, le=1)
    center_y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def fits_inside_image(self) -> BoundingBox:
        half_width = self.width / 2
        half_height = self.height / 2
        if not half_width <= self.center_x <= 1 - half_width:
            raise ValueError("bounding box exceeds image horizontally")
        if not half_height <= self.center_y <= 1 - half_height:
            raise ValueError("bounding box exceeds image vertically")
        return self


class Annotation(StrictModel):
    class_id: int = Field(ge=0, lt=len(EquipmentClass))
    equipment_class: EquipmentClass
    bounding_box: BoundingBox


class DatasetQualityReport(StrictModel):
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_count: int = Field(ge=0)
    readable_image_count: int = Field(ge=0)
    labeled_image_count: int = Field(ge=0)
    annotation_count: int = Field(ge=0)
    invalid_image_count: int = Field(ge=0)
    invalid_annotation_count: int = Field(ge=0)
    exact_duplicate_groups: list[list[str]]
    near_duplicate_groups: list[list[str]]
    class_counts: dict[EquipmentClass, int]
    image_modes: dict[str, int]
    width_range: tuple[int, int] | None
    height_range: tuple[int, int] | None
    training_ready: bool
    blockers: list[str]


class LabelImportReport(StrictModel):
    task_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    imported_image_count: int = Field(ge=0)
    annotation_count: int = Field(ge=0)
    missing_images: list[str]
    class_counts: dict[EquipmentClass, int]


class SplitEntry(StrictModel):
    relative_path: str
    split: str = Field(pattern=r"^(train|validation|test)$")
    group_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SplitManifest(StrictModel):
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int
    entries: list[SplitEntry]
    counts: dict[str, int]


class ExportConfig(StrictModel):
    format: str = "onnx"
    dynamic: bool = True
    simplify: bool = True


class PromotionGate(StrictModel):
    map50_95_min: float = Field(ge=0, le=1)
    precision_min: float = Field(ge=0, le=1)
    recall_min: float = Field(ge=0, le=1)
    max_regression_from_champion: float = Field(ge=0, le=1)


class DetectorAugmentation(StrictModel):
    """Scene-level, label-preserving YOLO transforms. Never changes schedule labels."""

    hsv_h: float = Field(default=0.015, ge=0, le=0.5)
    hsv_s: float = Field(default=0.7, ge=0, le=1)
    hsv_v: float = Field(default=0.4, ge=0, le=1)
    degrees: float = Field(default=0, ge=0, le=45)
    translate: float = Field(default=0.1, ge=0, le=1)
    scale: float = Field(default=0.5, ge=0, le=1)
    fliplr: float = Field(default=0.5, ge=0, le=1)
    mosaic: float = Field(default=1, ge=0, le=1)
    mixup: float = Field(default=0, ge=0, le=1)


class ExperimentConfig(StrictModel):
    name: str
    description: str
    base_model: str
    image_size: int = Field(gt=0)
    epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    patience: int = Field(ge=0)
    workers: int = Field(ge=0)
    device: str
    seed: int
    deterministic: bool
    amp: bool
    cache: bool
    augmentation: DetectorAugmentation = Field(default_factory=DetectorAugmentation)
    export: ExportConfig
    promotion_gate: PromotionGate


class CropAugmentation(StrictModel):
    """Machine-crop transforms only. Validation and test crops remain untouched."""

    variants_per_train_crop: int = Field(default=2, ge=0, le=8)
    brightness_min: float = Field(default=0.75, gt=0, le=1)
    brightness_max: float = Field(default=1.25, ge=1, le=2)
    contrast_min: float = Field(default=0.8, gt=0, le=1)
    contrast_max: float = Field(default=1.2, ge=1, le=2)
    horizontal_flip_probability: float = Field(default=0.5, ge=0, le=1)
    blur_probability: float = Field(default=0.15, ge=0, le=1)
    context_fraction: float = Field(default=0.1, ge=0, le=0.5)


class ClassifierExperimentConfig(StrictModel):
    name: str
    description: str
    base_model: str
    image_size: int = Field(gt=0)
    epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    patience: int = Field(ge=0)
    workers: int = Field(ge=0)
    device: str
    seed: int
    deterministic: bool
    amp: bool
    cache: bool
    augmentation: CropAugmentation
    export: ExportConfig
    top1_gate_min: float = Field(ge=0, le=1)
    macro_f1_gate_min: float = Field(ge=0, le=1)


class ModelManifest(StrictModel):
    task: Literal["detect", "classify"] = "detect"
    class_names: list[EquipmentClass]
    model_name: str
    run_id: str
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str
    source_model: str
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: dict[str, float]
    promotion_gate_passed: bool
