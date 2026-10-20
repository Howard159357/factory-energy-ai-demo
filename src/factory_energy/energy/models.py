from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# A reading row as returned by the storage layer: meter_id, ts, kw, kwh, ...
Reading = dict[str, Any]


@dataclass(frozen=True)
class MetricResult:
    value: float | None
    unit: str
    start: datetime | None = None
    end: datetime | None = None
    complete: bool = True
    coverage_ratio: float = 1.0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlantSnapshot:
    as_of: datetime
    plant_kw: float | None
    complete: bool
    expected_meter_count: int
    available_meter_count: int
    missing_meter_ids: list[str]
    stale_meter_ids: list[str]
    feeder_values: dict[str, float]
    warnings: list[str]


@dataclass(frozen=True)
class EnergySummary:
    start: datetime
    end: datetime
    plant_kwh: MetricResult
    meter_energy_results: dict[str, MetricResult]
    problem_meter_ids: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class RankingItem:
    rank: int
    meter_id: str
    value: float
    unit: str
    share_of_plant: float | None
