from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from factory_energy.energy.models import EnergySummary, MetricResult, Reading


def meter_energy(
    rows: Iterable[Reading], meter_id: str, start: datetime, end: datetime
) -> MetricResult:
    """kWh consumed between start and end from the cumulative kWh register."""
    selected = sorted(
        (
            r for r in rows
            if r["meter_id"] == meter_id and start <= r["ts"] <= end and r.get("kwh") is not None
        ),
        key=lambda r: r["ts"],
    )
    if len(selected) < 2:
        return MetricResult(None, "kWh", start, end, False, 0.0, ["ENERGY_BOUNDARY_MISSING"])
    first, last = selected[0], selected[-1]
    delta = float(last["kwh"]) - float(first["kwh"])
    if delta < 0:
        return MetricResult(
            None, "kWh", first["ts"], last["ts"], False, 0.0,
            ["KWH_DECREASE", "KWH_RESET_SUSPECTED"],
        )
    complete = first["ts"] == start and last["ts"] == end
    return MetricResult(
        delta, "kWh", first["ts"], last["ts"], complete, 1.0 if complete else 0.0,
        [] if complete else ["ENERGY_BOUNDARY_MISSING"],
    )


def plant_energy(
    rows: Iterable[Reading], feeder_ids: list[str], start: datetime, end: datetime
) -> EnergySummary:
    materialized = list(rows)
    results = {m: meter_energy(materialized, m, start, end) for m in feeder_ids}
    problems = [m for m, r in results.items() if not r.complete or r.value is None]
    value = None if problems else sum(r.value for r in results.values() if r.value is not None)
    warnings = sorted({w for r in results.values() for w in r.warnings})
    plant = MetricResult(
        value, "kWh", start, end, not problems, 0.0 if problems else 1.0, warnings
    )
    return EnergySummary(start, end, plant, results, problems, warnings)
