from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from factory_energy.energy.models import Reading


@dataclass(frozen=True)
class MinuteTotal:
    kw: float | None
    available: int
    complete: bool


def is_fresh(reading_ts: datetime, as_of: datetime, stale_after_seconds: int) -> bool:
    return (as_of - reading_ts).total_seconds() <= stale_after_seconds


def minute_plant_totals(
    rows: Iterable[Reading], feeder_ids: list[str]
) -> dict[datetime, MinuteTotal]:
    """Sum feeder kW per minute; a minute is complete only when every feeder reported."""
    expected = set(feeder_ids)
    grouped: dict[datetime, dict[str, float]] = {}
    for row in rows:
        if row["meter_id"] not in expected or row.get("kw") is None:
            continue
        minute = row["ts"].replace(second=0, microsecond=0)
        grouped.setdefault(minute, {})[row["meter_id"]] = float(row["kw"])
    totals: dict[datetime, MinuteTotal] = {}
    for minute, values in grouped.items():
        complete = set(values) >= expected
        totals[minute] = MinuteTotal(
            sum(values.values()) if complete else None, len(values), complete
        )
    return totals
