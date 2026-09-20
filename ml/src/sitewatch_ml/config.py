from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from sitewatch_ml.models import ExperimentConfig, PipelineConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?}")


def load_pipeline_config(path: Path | None = None) -> PipelineConfig:
    config_path = path or PROJECT_ROOT / "config" / "base.yaml"
    payload = _load_yaml(config_path)
    payload = _expand_env(payload)
    config = PipelineConfig.model_validate(payload)
    config.paths = config.paths.model_copy(
        update={
            field: _resolve_project_path(value)
            for field, value in config.paths.model_dump().items()
        }
    )
    return config


def load_experiment_config(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(_expand_env(_load_yaml(path)))


def _resolve_project_path(value: Path | str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return payload


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.groups()
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ValueError(f"required environment variable {name} is missing")

    return _ENV_PATTERN.sub(replace, value)
