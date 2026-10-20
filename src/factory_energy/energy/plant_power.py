from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from factory_energy.energy.completeness import is_fresh
from factory_energy.energy.models import PlantSnapshot, Reading


def current_plant_kw(
    rows: Iterable[Reading],
    feeder_ids: list[str],
    as_of: datetime,
    stale_after_seconds: int = 180,
) -> PlantSnapshot:
    latest: dict[str, Reading] = {}
    for row in rows:
        meter = row["meter_id"]
        if meter in feeder_ids and row["ts"] <= as_of and (
            meter not in latest or row["ts"] > latest[meter]["ts"]
        ):
            latest[meter] = row
    stale = [m for m, r in latest.items() if not is_fresh(r["ts"], as_of, stale_after_seconds)]
    values = {
        m: float(r["kw"]) for m, r in latest.items() if r.get("kw") is not None and m not in stale
    }
    missing = [meter for meter in feeder_ids if meter not in values]
    complete = not missing
    warnings = [] if complete else ["PLANT_TOTAL_INCOMPLETE"]
    if stale:
        warnings.append("STALE_METER")
    return PlantSnapshot(
        as_of=as_of,
        plant_kw=sum(values.values()) if complete else None,
        complete=complete,
        expected_meter_count=len(feeder_ids),
        available_meter_count=len(values),
        missing_meter_ids=missing,
        stale_meter_ids=stale,
        feeder_values=values,
        warnings=warnings,
    )
