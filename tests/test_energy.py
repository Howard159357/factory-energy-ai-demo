from datetime import datetime, timedelta

from factory_energy.energy.demand import (
    contract_usage,
    fixed_demand,
    interval_start,
    partial_demand,
    peak_demand,
)
from factory_energy.energy.energy_usage import meter_energy, plant_energy
from factory_energy.energy.models import Reading
from factory_energy.energy.plant_power import current_plant_kw
from factory_energy.energy.ranking import rank_meters

FEEDERS = [f"MDB-{i}" for i in range(1, 7)]
START = datetime(2026, 3, 2, 8, 0)


def rows(minutes: int = 15) -> list[Reading]:
    return [
        {"meter_id": m, "ts": START + timedelta(minutes=i), "kw": float(n + 1), "kwh": float(i + n)}
        for i in range(minutes + 1)
        for n, m in enumerate(FEEDERS)
    ]


def test_current_kw_freshness_and_missing_meter() -> None:
    assert current_plant_kw(rows(0), FEEDERS, START).plant_kw == 21
    stale = current_plant_kw(rows(0), FEEDERS, START + timedelta(seconds=181))
    assert not stale.complete and stale.stale_meter_ids == FEEDERS
    partial = current_plant_kw([r for r in rows(0) if r["meter_id"] != "MDB-6"], FEEDERS, START)
    assert partial.plant_kw is None and partial.missing_meter_ids == ["MDB-6"]


def test_energy_delta_and_reset() -> None:
    assert meter_energy(rows(), "MDB-1", START, START + timedelta(minutes=15)).value == 15
    assert plant_energy(rows(), FEEDERS, START, START + timedelta(minutes=15)).plant_kwh.value == 90
    bad = [
        {"meter_id": "MDB-1", "ts": START, "kwh": 10.0},
        {"meter_id": "MDB-1", "ts": START + timedelta(minutes=15), "kwh": 5.0},
    ]
    reset = meter_energy(bad, "MDB-1", START, START + timedelta(minutes=15))
    assert reset.value is None and "KWH_RESET_SUSPECTED" in reset.warnings


def test_demand_windows() -> None:
    demand = fixed_demand(rows(), FEEDERS, START)
    assert demand.complete and demand.value == 21
    assert interval_start(datetime(2026, 3, 2, 8, 29, 40)) == datetime(2026, 3, 2, 8, 15)
    in_progress = partial_demand(rows(), FEEDERS, START + timedelta(minutes=5))
    assert in_progress.value == 21 and in_progress.coverage_ratio == 5 / 15
    gap = [r for r in rows() if r["ts"] != START + timedelta(minutes=3)]
    assert not fixed_demand(gap, FEEDERS, START).complete
    assert peak_demand([demand]).value == 21


def test_contract_usage_and_ranking() -> None:
    assert contract_usage(1260, 1400) == (0.9, 140)
    assert contract_usage(None, 1400) == (None, None)
    ranking = rank_meters({"MDB-1": 200.0, "MDB-4": 500.0}, "kW", 700.0)
    assert ranking[0].meter_id == "MDB-4" and ranking[0].share_of_plant == 500 / 700
