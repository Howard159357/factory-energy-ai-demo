from __future__ import annotations

from dataclasses import astuple, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MinuteReading:
    meter_id: str
    ts: datetime
    kwh: float | None = None
    kw: float | None = None
    pf: float | None = None
    r_v: float | None = None
    s_v: float | None = None
    t_v: float | None = None
    r_a: float | None = None
    s_a: float | None = None
    t_a: float | None = None
    status: int | None = None

    def as_row(self) -> tuple[Any, ...]:
        return astuple(self)
