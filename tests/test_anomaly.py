from collections.abc import Iterator
from datetime import date, datetime, timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest

from factory_energy.anomaly.baseline import cusum_drift
from factory_energy.anomaly.data import PlantData, load_plant_data, runs
from factory_energy.anomaly.evaluate import Truth, evaluate, matches
from factory_energy.anomaly.ml import daily_features, day_scores, isolation_forest
from factory_energy.anomaly.models import Detection, Layer
from factory_energy.anomaly.rules import (
    demand_exceedance,
    low_power_factor,
    off_schedule_running,
    simultaneous_starts,
)
from factory_energy.anomaly.service import load_truths, run_detection
from factory_energy.config.loader import load_meters, load_settings
from factory_energy.simulator.generator import SimulationConfig, run_simulation
from factory_energy.simulator.scenarios import load_scenarios

SCENARIOS = {s.id: s for s in load_scenarios()}


@pytest.fixture(scope="module")
def autumn() -> Iterator[duckdb.DuckDBPyConnection]:
    """Four weeks around the S5 weekend plus the S8 capacitor fault."""
    connection = duckdb.connect(":memory:")
    config = SimulationConfig(date(2025, 10, 13), 28, 42, (SCENARIOS["S5"], SCENARIOS["S8"]))
    run_simulation(connection, config, load_settings(), load_meters())
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def autumn_data(autumn: duckdb.DuckDBPyConnection) -> PlantData:
    demand = load_settings().demand
    return load_plant_data(autumn, demand.contract_capacity_kw, demand.interval_minutes)


def test_runs_bridge_short_gaps() -> None:
    mask = pd.Series([0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1], dtype=bool)
    assert runs(mask, min_length=3, max_gap=1) == [(1, 7)]
    assert runs(mask, min_length=3) == [(4, 7)]


def test_off_schedule_finds_the_oven_left_on(autumn_data: PlantData) -> None:
    found = off_schedule_running(autumn_data)
    assert [d.meter_ids for d in found] and all(d.meter_ids == ("RF-02",) for d in found)
    assert min(d.start for d in found) < datetime(2025, 10, 18, 6)
    assert max(d.end for d in found) > datetime(2025, 10, 19, 18)


def test_low_power_factor_covers_the_fault(autumn_data: PlantData) -> None:
    found = low_power_factor(autumn_data)
    assert {d.meter_ids for d in found} == {("MDB-3",)}
    assert min(d.start for d in found) <= datetime(2025, 11, 3, 9, 30)
    assert all(d.score < 0.9 for d in found)


def test_no_false_alarms_on_a_normal_month(autumn_data: PlantData) -> None:
    assert simultaneous_starts(autumn_data) == []
    assert demand_exceedance(autumn_data) == []


def test_simultaneous_start_and_demand_rule() -> None:
    connection = duckdb.connect(":memory:")
    run_simulation(
        connection, SimulationConfig(date(2025, 6, 16), 1, 42, (SCENARIOS["S2"],)),
        load_settings(), load_meters(),
    )
    demand = load_settings().demand
    data = load_plant_data(connection, demand.contract_capacity_kw, demand.interval_minutes)
    starts = simultaneous_starts(data)
    assert len(starts) == 1 and {"IM-01", "RF-01", "CH-02"} <= set(starts[0].meter_ids)
    assert abs(starts[0].start - datetime(2025, 6, 16, 8)) <= timedelta(minutes=3)
    assert {d.start.hour for d in demand_exceedance(data)} == {8}


def test_cusum_flags_a_drift_and_ignores_noise() -> None:
    days = pd.date_range("2025-01-01", periods=80, freq="D").date
    rng = np.random.default_rng(1)
    kw = 50 + rng.normal(0, 0.5, 80)
    kw[40:60] += np.linspace(0, 12, 20)  # leak grows, then is repaired on day 60
    frame = pd.DataFrame({"kw": kw, "kind": "after_workday"}, index=days)
    episodes = cusum_drift(frame)
    assert len(episodes) == 1
    onset, end, excess, alarm = episodes[0]
    assert onset < alarm < end
    assert onset.date() <= days[46] and end.date() >= days[59] and excess > 8
    calm = frame.assign(kw=50 + rng.normal(0, 0.5, 80))
    assert cusum_drift(calm) == []


def test_matching_and_scores() -> None:
    t0 = datetime(2025, 6, 16, 8)
    truth = Truth("S2-X", "SIMULTANEOUS_START", ("IM-01", "RF-01"), t0, t0 + timedelta(minutes=45))
    hit = Detection(Layer.RULE, "r", "SIMULTANEOUS_START", ("RF-01",), t0, t0, "high", 1, "")
    wrong_type = Detection(Layer.RULE, "r", "LOW_POWER_FACTOR", ("RF-01",), t0, t0, "m", 1, "")
    late = Detection(Layer.RULE, "r", "SIMULTANEOUS_START", ("RF-01",), t0 + timedelta(hours=2),
                     t0 + timedelta(hours=3), "high", 1, "")
    assert matches(hit, truth) and not matches(wrong_type, truth) and not matches(late, truth)
    row = evaluate([hit, late], [truth])[0]
    assert (row.detections, row.true_positives, row.found, row.labels) == (2, 1, 1, 1)
    assert row.precision == 0.5 and row.recall == 1.0


def test_isolation_forest_ranks_the_odd_oven_weekend_first(autumn_data: PlantData) -> None:
    features = daily_features(autumn_data, "RF-02")
    ranked = features.index[np.argsort(-day_scores(features))]
    assert set(ranked[:2]) == {date(2025, 10, 18), date(2025, 10, 19)}
    assert all(d.layer is Layer.ML for d in isolation_forest(autumn_data))


def test_run_detection_persists_and_scores(autumn: duckdb.DuckDBPyConnection) -> None:
    detections, scores = run_detection(autumn, load_settings(), use_ml=False)
    stored = autumn.execute("SELECT COUNT(*) FROM detections").fetchone()
    assert stored == (len(detections),)
    by_name = {s.name: s for s in scores}
    assert by_name["OFF_SCHEDULE_RUNNING"].recall == 1.0
    assert by_name["LOW_POWER_FACTOR"].recall == 1.0
    assert len(load_truths(autumn)) == 2
