"""Versioned adapter from training labels to the stable SiteWatch rule taxonomy."""

import math
from typing import Literal

# Exact order is checked against the classifier checkpoint at startup.
TRAINING_CLASSES = (
    "dump_truck",
    "excavator",
    "motor_grader",
    "roller",
    "crane_manipulator",
    "light_commercial_vehicle",
    "forklift",
    "bucket_loader",
    "concrete_mixer",
    "tanker",
    "bulldozer",
    "cleaning_equipment",
    "truck",
    "trailer",
    "mobile_crane",
    "tower_crane",
    "tractor",
    "concrete_pump",
    "drilling_rig",
    "pile_driver",
    "person",
    "other_vehicle",
)

# Keep the raw label even when multiple classifier labels converge on one rule class.
RULE_CLASSES = {
    "dump_truck": "dump_truck",
    "excavator": "excavator",
    "roller": "road_roller",
    "crane_manipulator": "loader_crane",
    "concrete_mixer": "concrete_mixer",
    "bulldozer": "bulldozer",
    "truck": "truck",
    "mobile_crane": "mobile_crane",
    "tower_crane": "tower_crane",
    "drilling_rig": "piling_rig",
    "pile_driver": "piling_rig",
    "concrete_pump": "concrete_pump",
    "bucket_loader": "bucket_loader",
}

MappingStatus = Literal["mapped", "other", "ignored", "low_confidence"]


def map_class(
    raw_class: str, score: float, minimum_score: float
) -> tuple[str | None, MappingStatus]:
    """Unmapped/uncertain objects must never become automatic rule violations."""
    if raw_class == "person":
        return None, "ignored"
    if not math.isfinite(score) or score < minimum_score:
        return None, "low_confidence"
    canonical = RULE_CLASSES.get(raw_class)
    return (canonical, "mapped") if canonical else (None, "other")


def validate_training_classes(names: dict[str, str]) -> None:
    expected = {str(index): name for index, name in enumerate(TRAINING_CLASSES)}
    if names != expected:
        raise ValueError("Classifier class_names do not match the reviewed SiteWatch adapter")
