import pytest

from sitewatch_inference.taxonomy import TRAINING_CLASSES, map_class, validate_training_classes


def test_training_order_matches_expected_checkpoint() -> None:
    validate_training_classes({str(index): name for index, name in enumerate(TRAINING_CLASSES)})
    with pytest.raises(ValueError):
        validate_training_classes({"0": "excavator"})


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("roller", "road_roller"),
        ("crane_manipulator", "loader_crane"),
        ("drilling_rig", "piling_rig"),
        ("pile_driver", "piling_rig"),
        ("dump_truck", "dump_truck"),
        ("truck", "truck"),
        ("concrete_pump", "concrete_pump"),
        ("bucket_loader", "bucket_loader"),
    ],
)
def test_canonical_aliases(raw: str, canonical: str) -> None:
    assert map_class(raw, 0.9, 0.5) == (canonical, "mapped")


def test_other_and_uncertain_are_not_rule_eligible() -> None:
    assert map_class("motor_grader", 0.9, 0.5) == (None, "other")
    assert map_class("excavator", 0.3, 0.5) == (None, "low_confidence")
    assert map_class("excavator", float("nan"), 0.5) == (None, "low_confidence")
    assert map_class("person", 0.99, 0.5) == (None, "ignored")
