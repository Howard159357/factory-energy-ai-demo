from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Layer(StrEnum):
    RULE = "RULE"
    BASELINE = "BASELINE"
    ML = "ML"


@dataclass(frozen=True)
class Detection:
    layer: Layer
    detector: str
    event_type: str
    meter_ids: tuple[str, ...]
    start: datetime
    end: datetime
    severity: str
    score: float
    message: str
    detected_at: datetime | None = None  # when the detector could first have raised it

    @property
    def seen_at(self) -> datetime:
        return self.detected_at or self.start

    @property
    def detection_id(self) -> str:
        meters = "+".join(self.meter_ids)
        return f"{self.detector}:{meters}:{self.start:%Y%m%d%H%M}"
