from datetime import date, datetime

import duckdb
import numpy as np
import pytest
from pydantic import ValidationError

from factory_energy.config.loader import load_meters, load_settings
from factory_energy.simulator.generator import SimulationConfig, run_simulation, simulate
from factory_energy.simulator.scenarios import (
    Scenario,
    build_effects,
    load_scenarios,
)
from factory_energy.simulator.timeline import Timeline

SCENARIOS = {scenario.id: scenario for scenario in load_scenarios()}


def series(start: date, days: int, *ids: str) -> dict[str, np.ndarray]:
    config = SimulationConfig(start, days, 42, tuple(SCENARIOS[i] for i in ids))
    return {meter: s.kw for meter, s in simulate(config, load_settings(), load_meters())}


def test_scenario_files_load() -> None:
    assert sorted(SCENARIOS) == ["S1", "S2", "S3", "S4", "S5", "S8"]
    for scenario in SCENARIOS.values():
        assert scenario.replay.start < scenario.replay.end


def test_invalid_scenarios_are_rejected() -> None:
    base = {"id": "S9", "title": "t", "description": "d",
            "replay": {"start": "2025-01-01T00:00", "end": "2025-01-02T00:00"}}
    with pytest.raises(ValidationError):
        Scenario.model_validate({**base, "events": [{"type": "meteor_strike"}]})
    with pytest.raises(ValidationError):
        Scenario.model_validate({**base, "events": [{
            "type": "air_leak", "start": "2025-01-02T00:00", "full_at": "2025-01-01T00:00",
            "repaired_at": "2025-01-03T00:00", "max_kw": 5}]})
    bad = Scenario.model_validate({**base, "events": [{
        "type": "left_running", "meter": "XX-99", "start": "2025-01-01T00:00",
        "end": "2025-01-01T05:00", "level": 0.3}]})
    with pytest.raises(ValueError, match="unknown meter"):
        build_effects(Timeline(date(2025, 1, 1), 1), [bad], load_meters())


def test_simultaneous_start_exceeds_contract_and_is_labelled() -> None:
    connection = duckdb.connect(":memory:")
    config = SimulationConfig(date(2025, 6, 16), 1, 42, (SCENARIOS["S2"],))
    summary = run_simulation(connection, config, load_settings(), load_meters())
    assert summary.peak_demand_kw > load_settings().demand.contract_capacity_kw
    assert summary.peak_demand_start in (datetime(2025, 6, 16, 8, 0), datetime(2025, 6, 16, 8, 15))
    labels = connection.execute(
        "SELECT scenario_id, event_type FROM ground_truth_events ORDER BY start_ts, event_type"
    ).fetchall()
    assert ("S2", "SIMULTANEOUS_START") in labels and ("S2", "DEMAND_EXCEEDANCE") in labels
    baseline = series(date(2025, 6, 16), 1)
    plant = np.sum([baseline[f"MDB-{i}"] for i in range(1, 7)], axis=0)
    assert plant.reshape(-1, 15).mean(axis=1).max() < load_settings().demand.contract_capacity_kw


def test_a_day_is_identical_whatever_the_simulation_window() -> None:
    short = series(date(2025, 6, 16), 1)
    long = series(date(2025, 6, 9), 14)
    day = slice(7 * 1440, 8 * 1440)
    for meter in ("MDB-4", "BI-01", "RF-02", "EV-01", "AC-01"):
        assert np.allclose(short[meter], long[meter][day]), meter


def test_heat_wave_only_changes_its_days() -> None:
    effects = build_effects(Timeline(date(2025, 7, 21), 5), [SCENARIOS["S3"]], load_meters())
    delta = effects.temperature_delta.reshape(5, 1440)
    assert delta[0].max() == 0 and delta[4].max() == 0
    assert 5.0 < delta[1:4].max() <= 5.5


def test_air_leak_ramps_then_stops_after_repair() -> None:
    effects = build_effects(Timeline(date(2025, 9, 1), 35), [SCENARIOS["S4"]], load_meters())
    leak = effects.air_demand_delta
    assert leak.max() == pytest.approx(18.0)
    assert leak[:360].max() == 0 and leak[-1440:].max() == 0
    with_leak = series(date(2025, 9, 21), 1, "S4")
    without = series(date(2025, 9, 21), 1)
    compressors = ("AC-01", "AC-02", "AC-03")
    assert sum(with_leak[m].sum() for m in compressors) > sum(without[m].sum() for m in compressors)


def test_left_running_oven_keeps_consuming_all_weekend() -> None:
    with_fault = series(date(2025, 10, 17), 3, "S5")["RF-02"]
    normal = series(date(2025, 10, 17), 3)["RF-02"]
    weekend = slice(1440 + 18 * 60, 3 * 1440)  # Saturday 18:00 .. Sunday 24:00
    assert normal[weekend].max() < 5
    assert with_fault[weekend].min() > 20  # 36 % of a 70 kW oven


def test_capacitor_fault_lowers_feeder_power_factor() -> None:
    config = SimulationConfig(date(2025, 11, 4), 1, 42, (SCENARIOS["S8"],))
    feeders = {m: s for m, s in simulate(config, load_settings(), load_meters()) if m == "MDB-3"}
    clean = SimulationConfig(date(2025, 11, 4), 1, 42)
    normal = {m: s for m, s in simulate(clean, load_settings(), load_meters()) if m == "MDB-3"}
    day = slice(9 * 60, 17 * 60)
    assert np.nanmean(feeders["MDB-3"].pf[day]) < 0.87 < 0.94 < np.nanmean(normal["MDB-3"].pf[day])
    assert np.array_equal(feeders["MDB-3"].kw, normal["MDB-3"].kw)
