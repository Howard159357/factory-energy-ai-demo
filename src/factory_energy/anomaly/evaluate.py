"""Score detections against the simulator's ground-truth labels."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from factory_energy.anomaly.models import Detection, Layer

# Ground-truth types that describe a fault or an avoidable event (HEAT_WAVE is context only).
SCORED_TYPES = (
    "SIMULTANEOUS_START", "DEMAND_EXCEEDANCE", "OFF_SCHEDULE_RUNNING", "LOW_POWER_FACTOR",
    "AIR_LEAK",
)
TOLERANCE = timedelta(minutes=30)


@dataclass(frozen=True)
class Truth:
    event_id: str
    event_type: str
    meter_ids: tuple[str, ...]
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Score:
    name: str
    detections: int
    true_positives: int
    labels: int
    found: int
    median_delay: timedelta | None

    @property
    def precision(self) -> float | None:
        return self.true_positives / self.detections if self.detections else None

    @property
    def recall(self) -> float | None:
        return self.found / self.labels if self.labels else None


def matches(detection: Detection, truth: Truth) -> bool:
    overlaps = (
        detection.start < truth.end + TOLERANCE and truth.start - TOLERANCE < detection.end
    )
    if not overlaps:
        return False
    if detection.layer is Layer.ML:  # ML flags "something unusual", not a specific fault
        return bool(set(detection.meter_ids) & _related(truth))
    return detection.event_type == truth.event_type and bool(
        set(detection.meter_ids) & set(truth.meter_ids) or "PLANT" in truth.meter_ids
    )


def _related(truth: Truth) -> set[str]:
    """Equipment that physically shares the fault (sub-meters under a labelled feeder)."""
    related = set(truth.meter_ids)
    if "MDB-5" in related:
        related |= {"AC-01", "AC-02", "AC-03", "DR-01"}
    if "MDB-3" in related:
        related |= {"IM-01", "IM-02", "IM-03", "IM-04"}
    return related


def score(
    name: str, detections: Sequence[Detection], truths: Sequence[Truth]
) -> Score:
    hits = [d for d in detections if any(matches(d, t) for t in truths)]
    delays: list[timedelta] = []
    found = 0
    for truth in truths:
        matched = [d for d in detections if matches(d, truth)]
        if matched:
            found += 1
            delays.append(max(min(d.seen_at for d in matched) - truth.start, timedelta(0)))
    return Score(
        name, len(detections), len(hits), len(truths), found,
        timedelta(seconds=median(d.total_seconds() for d in delays)) if delays else None,
    )


def evaluate(detections: Sequence[Detection], truths: Sequence[Truth]) -> list[Score]:
    scored = [t for t in truths if t.event_type in SCORED_TYPES]
    rows = []
    for event_type in SCORED_TYPES:
        own = [d for d in detections if d.layer is not Layer.ML and d.event_type == event_type]
        rows.append(score(event_type, own, [t for t in scored if t.event_type == event_type]))
    for layer in Layer:
        own = [d for d in detections if d.layer is layer]
        rows.append(score(f"layer {layer.value}", own, scored))
    rows.append(score("all layers", list(detections), scored))
    return rows
