from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from enum import StrEnum

import numpy as np

from factory_energy.config.models import FactorySettings
from factory_energy.simulator.timeline import (
    MINUTES_PER_DAY,
    BoolArray,
    FloatArray,
    Timeline,
    rng_for,
)

OVERTIME_PROBABILITY = 0.6
# Start-time stagger (minutes, inclusive) by equipment prefix; molders preheat before the shift.
START_JITTER_MIN: dict[str, tuple[int, int]] = {"SM": (-10, 10), "WS": (-5, 15), "IM": (-75, 0)}


class DayType(StrEnum):
    WORKDAY = "WORKDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"
    HOLIDAY = "HOLIDAY"


def _minute(value: time) -> int:
    return value.hour * 60 + value.minute


@dataclass(frozen=True)
class ShiftTimes:
    day_start: int
    day_end: int
    overtime_end: int
    lunch_start: int
    lunch_end: int

    @classmethod
    def from_settings(cls, settings: FactorySettings) -> ShiftTimes:
        day, overtime = settings.shift("Day"), settings.shift("Overtime")
        lunch = settings.schedule.lunch_break
        return cls(
            _minute(day.start),
            _minute(day.end),
            _minute(overtime.end),
            _minute(lunch.start) if lunch else 0,
            _minute(lunch.end) if lunch else 0,
        )


@dataclass(frozen=True)
class ProductionPlan:
    """Which production equipment runs when, plus derived activity levels (0..1)."""

    timeline: Timeline
    day_types: list[DayType]
    overtime: list[bool]
    holiday_names: dict[date, str]
    running: dict[str, BoolArray]
    lunch: BoolArray
    office: FloatArray
    smt_activity: FloatArray
    molding_activity: FloatArray
    assembly_activity: FloatArray

    @property
    def plant_activity(self) -> FloatArray:
        return 0.4 * self.smt_activity + 0.4 * self.molding_activity + 0.2 * self.assembly_activity


def day_type(day: date, holidays: dict[date, str]) -> DayType:
    if day in holidays:
        return DayType.HOLIDAY
    if day.weekday() == 5:
        return DayType.SATURDAY
    return DayType.SUNDAY if day.weekday() == 6 else DayType.WORKDAY


def _start_shift(seed: int, timeline: Timeline, key: str, start: int, low: int, high: int) -> int:
    day = timeline.dates[min(max(start, 0) // MINUTES_PER_DAY, timeline.days - 1)]
    return int(rng_for(seed, "schedule", "start", key, day.isoformat()).integers(low, high + 1))


def build_plan(timeline: Timeline, settings: FactorySettings, seed: int) -> ProductionPlan:
    shifts = ShiftTimes.from_settings(settings)
    holidays = {h.date: h.name for h in settings.holidays}
    types = [day_type(day, holidays) for day in timeline.dates]
    overtime = [
        kind is DayType.WORKDAY
        and bool(rng_for(seed, "schedule", "overtime", day.isoformat()).random()
                 < OVERTIME_PROBABILITY)
        for day, kind in zip(timeline.dates, types, strict=True)
    ]

    windows: dict[str, list[tuple[int, int]]] = {
        key: [] for key in
        ("SMT-L1", "SMT-L2", "SMT-L3", "WS-01", "IM-01", "IM-02", "IM-03", "IM-04")
    }
    lunch: list[tuple[int, int]] = []
    office: list[tuple[int, int, float]] = []
    for offset, (kind, extra) in enumerate(zip(types, overtime, strict=True)):
        base = offset * MINUTES_PER_DAY
        day = (base + shifts.day_start, base + shifts.day_end)
        long_day = (base + shifts.day_start, base + shifts.overtime_end)
        around_clock = (base + shifts.day_start, base + shifts.day_start + MINUTES_PER_DAY)
        if kind is DayType.WORKDAY:
            windows["SMT-L1"].append(around_clock)
            windows["SMT-L2"].append(long_day if extra else day)
            windows["SMT-L3"].append(day)
            windows["WS-01"].append(day)
            windows["IM-01"].append(long_day)
            windows["IM-02"].append(long_day)
            windows["IM-03"].append(around_clock)
            windows["IM-04"].append(around_clock)
            lunch.append((base + shifts.lunch_start, base + shifts.lunch_end))
            office.append((base + shifts.day_start - 30, base + shifts.day_end + 30, 1.0))
        elif kind is DayType.SATURDAY:
            for key in ("SMT-L1", "SMT-L2", "IM-01", "IM-02"):
                windows[key].append(day)
            lunch.append((base + shifts.lunch_start, base + shifts.lunch_end))
            office.append((base + shifts.day_start, base + shifts.lunch_start, 0.3))

    # Operators do not start everything on the stroke of the shift: stagger start times.
    for key, spans in windows.items():
        low, high = START_JITTER_MIN.get(key[:2], (0, 0))
        windows[key] = [
            (start + _start_shift(seed, timeline, key, start, low, high), end)
            for start, end in spans
        ]

    running = {key: timeline.mask(spans) for key, spans in windows.items()}
    lunch_mask = timeline.mask(lunch)
    office_level = np.zeros(timeline.minutes)
    for start, end, level in office:
        office_level[start:end] = level

    def line_activity(keys: tuple[str, ...]) -> FloatArray:
        stacked = np.stack([running[key].astype(np.float64) for key in keys])
        return np.asarray(stacked.mean(axis=0) * np.where(lunch_mask, 0.4, 1.0))

    molder_weights = {"IM-01": 40.0, "IM-02": 40.0, "IM-03": 65.0, "IM-04": 90.0}
    molding = sum(running[k].astype(np.float64) * w for k, w in molder_weights.items())
    return ProductionPlan(
        timeline=timeline,
        day_types=types,
        overtime=overtime,
        holiday_names={d: n for d, n in holidays.items() if d in set(timeline.dates)},
        running=running,
        lunch=lunch_mask,
        office=office_level,
        smt_activity=line_activity(("SMT-L1", "SMT-L2", "SMT-L3")),
        molding_activity=np.asarray(molding / sum(molder_weights.values())),
        assembly_activity=np.asarray(
            0.6 * running["WS-01"] * np.where(lunch_mask, 0.5, 1.0) + 0.4 * (office_level > 0)
        ),
    )
