from sitewatch_ml.experiments import _passes_gate
from sitewatch_ml.models import ExperimentConfig


def test_promotion_gate_rejects_regression_from_champion() -> None:
    experiment = _experiment()
    metrics = {
        "metrics/mAP50-95(B)": 0.50,
        "metrics/precision(B)": 0.70,
        "metrics/recall(B)": 0.65,
    }

    assert _passes_gate(metrics, experiment, champion_map50_95=0.55) is False
    assert _passes_gate(metrics, experiment, champion_map50_95=0.52) is True


def test_promotion_gate_rejects_missing_required_metric() -> None:
    assert _passes_gate({"metrics/precision(B)": 0.90}, _experiment()) is False


def _experiment() -> ExperimentConfig:
    return ExperimentConfig.model_validate(
        {
            "name": "test",
            "description": "test",
            "base_model": "base.pt",
            "image_size": 640,
            "epochs": 1,
            "batch_size": 1,
            "patience": 0,
            "workers": 0,
            "device": "cpu",
            "seed": 1,
            "deterministic": True,
            "amp": False,
            "cache": False,
            "export": {"format": "onnx", "dynamic": True, "simplify": True},
            "promotion_gate": {
                "map50_95_min": 0.35,
                "precision_min": 0.55,
                "recall_min": 0.50,
                "max_regression_from_champion": 0.03,
            },
        }
    )
