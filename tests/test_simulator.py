from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pytest

from factory_energy.__main__ import main
from factory_energy.config.loader import load_meters, load_settings
from factory_energy.energy.demand import fixed_demand
from factory_energy.simulator.generator import SimulationConfig, run_simulation, simulate
from factory_energy.simulator.schedule import DayType, build_plan
from factory_energy.simulator.timeline import (
    Timeline,
    delay_starts,
    extend,
    minutes_since_on,
    rng_for,
)

# Mon 2025-07-07 .. Sun 2025-07-20: two summer weeks including weekends.
SUMMER = SimulationConfig(start=date(2025, 7, 7), days=14, seed=42)
FEEDERS = [f"MDB-{i}" for i in range(1, 7)]


@pytest.fixture(scope="module")
def db() -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(":memory:")
    run_simulation(connection, SUMMER, load_settings(), load_meters())
    yield connection
    connection.close()


def one(db: duckdb.DuckDBPyConnection, sql: str) -> float:
    row = db.execute(sql).fetchone()
    assert row is not None
    return float(row[0])


def test_timeline_helpers() -> None:
    on = np.array([0, 0, 1, 1, 0, 0, 0, 1, 1, 1], dtype=bool)
    assert extend(on, before=1, after=1).tolist() == [0, 1, 1, 1, 1, 0, 1, 1, 1, 1]
    assert minutes_since_on(on)[[2, 3, 7, 9]].tolist() == [0, 1, 0, 2]
    delayed = delay_starts(on, lambda minute: 1)
    assert delayed.tolist() == [0, 0, 0, 1, 0, 0, 0, 0, 1, 1]
    assert delayed.sum() <= on.sum() and not (delayed & ~on).any()
    assert Timeline(date(2025, 1, 1), 2).timestamps()[-1] == np.datetime64("2025-01-02T23:59")


def test_same_seed_same_data_and_streams_are_independent() -> None:
    config = SimulationConfig(start=date(2025, 3, 3), days=2, seed=7)
    settings, catalog = load_settings(), load_meters()
    first = dict(simulate(config, settings, catalog))
    second = dict(simulate(config, settings, catalog))
    for meter in ("RF-01", "CH-01", "MDB-4"):
        assert np.array_equal(first[meter].kw, second[meter].kw)
    other = dict(simulate(SimulationConfig(config.start, config.days, seed=8), settings, catalog))
    assert not np.array_equal(first["MDB-4"].kw, other["MDB-4"].kw)
    assert rng_for(1, "a").random() != rng_for(1, "b").random()


def test_calendar_marks_holidays_and_weekends() -> None:
    plan = build_plan(Timeline(date(2025, 10, 9), 4), load_settings(), seed=42)
    assert plan.day_types == [
        DayType.WORKDAY, DayType.HOLIDAY, DayType.SATURDAY, DayType.SUNDAY
    ]
    assert plan.holiday_names[date(2025, 10, 10)] == "National Day"


def test_every_meter_has_every_minute(db: duckdb.DuckDBPyConnection) -> None:
    rows = db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT meter_id), SUM((kw IS NULL)::INT) "
        "FROM meter_reading_minute"
    ).fetchone()
    assert rows == (29 * 14 * 1440, 29, 0)


def test_feeder_covers_its_sub_meters(db: duckdb.DuckDBPyConnection) -> None:
    unmetered = one(db, """
        WITH e AS (SELECT r.ts, m.feeder_id, SUM(r.kw) kw FROM meter_reading_minute r
                   JOIN meter_master m USING (meter_id) WHERE m.meter_type = 'EQUIPMENT'
                   GROUP BY 1, 2)
        SELECT MIN(f.kw - e.kw) FROM meter_reading_minute f
        JOIN e ON e.ts = f.ts AND e.feeder_id = f.meter_id""")
    assert unmetered > 0


def test_kwh_register_integrates_kw(db: duckdb.DuckDBPyConnection) -> None:
    worst = one(db, """
        SELECT MAX(gap) FROM (
            SELECT ABS((MAX(kwh) - MIN(kwh)) - (SUM(kw) - ARG_MAX(kw, ts)) / 60) gap
            FROM meter_reading_minute GROUP BY meter_id)""")
    assert worst < 0.5
    decreases = one(db, """
        SELECT COUNT(*) FROM (SELECT kwh < LAG(kwh) OVER (PARTITION BY meter_id ORDER BY ts) d
                              FROM meter_reading_minute) WHERE d""")
    assert decreases == 0


def test_phase_currents_match_power(db: duckdb.DuckDBPyConnection) -> None:
    ratio = one(db, """
        SELECT AVG((r_a + s_a + t_a) / 3 / (kw * 1000 / (sqrt(3) * (r_v + s_v + t_v) / 3 * pf)))
        FROM meter_reading_minute WHERE kw > 1""")
    assert ratio == pytest.approx(1.0, abs=0.005)
    pf = db.execute(
        "SELECT MIN(pf), MAX(pf) FROM meter_reading_minute WHERE meter_id LIKE 'MDB-%'"
    ).fetchone()
    assert pf is not None and pf[0] > 0.93 and pf[1] <= 1.0


def test_summer_demand_is_realistic(db: duckdb.DuckDBPyConnection) -> None:
    peak = db.execute("""
        SELECT time_bucket(INTERVAL 15 MINUTE, ts) w, SUM(kw) / 15 FROM meter_reading_minute
        WHERE meter_id LIKE 'MDB-%' GROUP BY 1 ORDER BY 2 DESC LIMIT 1""").fetchone()
    assert peak is not None
    window, demand = peak
    assert 1150 < demand < load_settings().demand.contract_capacity_kw
    rows = db.execute(
        "SELECT meter_id, ts, kw FROM meter_reading_minute WHERE meter_id LIKE 'MDB-%' "
        "AND ts >= ? AND ts < ?", (window, window + timedelta(minutes=15)),
    ).fetchall()
    engine = fixed_demand([{"meter_id": m, "ts": t, "kw": k} for m, t, k in rows], FEEDERS, window)
    assert engine.value == pytest.approx(demand)
    sunday = one(db, """SELECT AVG(kw) * 6 FROM meter_reading_minute
        WHERE meter_id LIKE 'MDB-%' AND ts >= '2025-07-13' AND ts < '2025-07-14'""")
    assert 300 < sunday < 550


def test_equipment_linkages(db: duckdb.DuckDBPyConnection) -> None:
    def mean_kw(meters: str, start: str, end: str) -> float:
        return one(db, f"""SELECT SUM(kw) / COUNT(DISTINCT ts) FROM meter_reading_minute
            WHERE meter_id IN ({meters}) AND ts >= '{start}' AND ts < '{end}'
            AND hour(ts) BETWEEN 9 AND 16""")

    compressors = "'AC-01','AC-02','AC-03'"
    assert mean_kw(compressors, "2025-07-08", "2025-07-09") > 2 * mean_kw(
        compressors, "2025-07-13", "2025-07-14"
    )
    burn_in = "'BI-01','BI-02'"
    assert mean_kw(burn_in, "2025-07-13", "2025-07-14") > 60  # runs through Sunday
    first_on = {
        meter: db.execute(
            f"SELECT MIN(ts) FROM meter_reading_minute WHERE meter_id = '{meter}' "
            "AND ts >= '2025-07-08 05:00' AND kw > 10"
        ).fetchone()
        for meter in ("RF-03", "SMT-L3")
    }
    oven, line = first_on["RF-03"], first_on["SMT-L3"]
    assert oven is not None and line is not None
    lead = (line[0] - oven[0]).total_seconds() / 60
    assert 30 <= lead <= 75


def test_simulate_cli_refuses_to_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "plant.duckdb"
    out.write_bytes(b"")
    assert main(["simulate", "--days", "1", "--out", str(out)]) == 2
    assert main(["simulate", "--start", "2025-01-06", "--days", "1", "--out", str(out),
                 "--force"]) == 0
    with duckdb.connect(str(out), read_only=True) as connection:
        row = connection.execute("SELECT COUNT(*) FROM meter_reading_minute").fetchone()
        assert row == (29 * 1440,)
        run = connection.execute("SELECT seed, days FROM simulation_runs").fetchone()
        assert run == (42, 1)
