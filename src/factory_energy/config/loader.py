from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from factory_energy.config.models import FactorySettings, MeterCatalog

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"YAML root must be a mapping: {path}")
    return value


def load_settings(path: Path = CONFIG_DIR / "factory.yaml") -> FactorySettings:
    return FactorySettings.model_validate(_read(path))


def load_meters(path: Path = CONFIG_DIR / "meters.yaml") -> MeterCatalog:
    return MeterCatalog.model_validate(_read(path))
