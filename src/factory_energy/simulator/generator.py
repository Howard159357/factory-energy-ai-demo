from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from factory_energy.config.models import FactorySettings, MeterCatalog
from factory_energy.simulator import SIMULATOR_VERSION
from factory_energy.simulator.electrical import (
    UNMETERED_PF,
    ElectricalSeries,
    build_series,
    equipment_pf,
    reactive_kvar,
)
from factory_energy.simulator.equipment import MODELS, SimContext, unmetered_load
from factory_energy.simulator.scenarios import (
    GroundTruthEvent,
    Scenario,
    build_effects,
    demand_exceedances,
)
from factory_energy.simulator.schedule import build_plan
from factory_energy.simulator.timeline import (
    MINUTES_PER_DAY,
    FloatArray,
    RandomSource,
    Timeline,
    rng_for,
)
from factory_energy.simulator.weather import outdoor_temperature
from factory_energy.storage.repository import LocalRepository
from factory_energy.storage.schema import initialize_schema

PAD_DAYS = 1
READING_COLUMNS = [
    "meter_id", "ts", "kwh", "kw", "pf", "r_v", "s_v", "t_v", "r_a", "s_a", "t_a", "status",
]


@dataclass(frozen=True)
class SimulationConfig:
    start: date
    days: int
    seed: int = 42
    scenarios: tuple[Scenario, ...] = ()


@dataclass(frozen=True)
class SimulationSummary:
    run_id: str
    meters: int
    rows: int
    peak_demand_kw: float
    labelled_events: int
    exceedance_intervals: int
    peak_demand_start: datetime
    night_base_kw: float
    plant_mwh: float
    elapsed_seconds: float


def _series(
    seed: int, timeline: Timeline, meter_id: str, kw: FloatArray, kvar: FloatArray
) -> ElectricalSeries:
    register_start = float(rng_for(seed, meter_id, "register").uniform(1e5, 9e5))
    rand = RandomSource(seed, timeline, (meter_id, "electrical"))
    full = build_series(kw, kvar, rand, register_start)
    inner = slice(PAD_DAYS * MINUTES_PER_DAY, -PAD_DAYS * MINUTES_PER_DAY)
    return ElectricalSeries(
        kw=full.kw[inner], kvar=full.kvar[inner], pf=full.pf[inner],
        voltages=(full.voltages[0][inner], full.voltages[1][inner], full.voltages[2][inner]),
        currents=(full.currents[0][inner], full.currents[1][inner], full.currents[2][inner]),
        kwh=full.kwh[inner],
    )


def padded(config: SimulationConfig) -> Timeline:
    """The requested window plus one day on each side.

    Equipment that runs across midnight, preheats before a shift or follows multi-day weather
    needs its neighbouring days; simulating them and trimming afterwards makes every day
    identical no matter which window it was simulated in.
    """
    return Timeline(config.start - timedelta(days=PAD_DAYS), config.days + 2 * PAD_DAYS)


def simulate(
    config: SimulationConfig, settings: FactorySettings, catalog: MeterCatalog
) -> Iterator[tuple[str, ElectricalSeries]]:
    """Yield (meter_id, series) for every equipment meter, then every feeder meter."""
    timeline = padded(config)
    plan = build_plan(timeline, settings, config.seed)
    effects = build_effects(timeline, list(config.scenarios), catalog)
    temperature = outdoor_temperature(timeline, config.seed) + effects.temperature_delta
    ctx = SimContext(timeline, plan, temperature, effects.air_demand_delta)
    feeder_kw = {f.meter_id: np.zeros(timeline.minutes) for f in catalog.feeders}
    feeder_kvar = {f.meter_id: np.zeros(timeline.minutes) for f in catalog.feeders}

    for spec in catalog.equipment:
        model = MODELS.get(spec.category)
        if model is None:
            raise KeyError(f"no load model for category {spec.category!r}")
        kw = model(ctx, spec, RandomSource(config.seed, timeline, (spec.meter_id, "load")))
        kw = np.clip(effects.apply(spec, kw, config.seed), 0.0, None)
        kvar = reactive_kvar(kw, equipment_pf(kw, spec.rated_kw, spec.category))
        feeder_kw[spec.feeder] += kw
        feeder_kvar[spec.feeder] += kvar
        yield spec.meter_id, _series(config.seed, timeline, spec.meter_id, kw, kvar)

    unmetered_tan = float(np.tan(np.arccos(UNMETERED_PF)))
    for feeder in catalog.feeders:
        rand = RandomSource(config.seed, timeline, (feeder.meter_id, "load"))
        extra = unmetered_load(ctx, feeder.meter_id, rand)
        kw = feeder_kw[feeder.meter_id] + extra
        kvar = feeder_kvar[feeder.meter_id] + extra * unmetered_tan
        kvar = kvar * (1 - effects.feeder_compensation(feeder.meter_id))
        yield feeder.meter_id, _series(config.seed, timeline, feeder.meter_id, kw, kvar)


def _temperature(config: SimulationConfig, catalog: MeterCatalog) -> FloatArray:
    timeline = padded(config)
    delta = build_effects(timeline, list(config.scenarios), catalog).temperature_delta
    full = outdoor_temperature(timeline, config.seed) + delta
    return np.asarray(np.round(full[PAD_DAYS * MINUTES_PER_DAY:-PAD_DAYS * MINUTES_PER_DAY], 2))


def _frame(meter_id: str, timestamps: pd.DatetimeIndex, series: ElectricalSeries) -> pd.DataFrame:
    v, a = series.voltages, series.currents
    frame = pd.DataFrame(
        {
            "meter_id": meter_id,
            "ts": timestamps,
            "kwh": np.round(series.kwh, 3),
            "kw": np.round(series.kw, 3),
            "pf": np.round(series.pf, 3),
            "r_v": np.round(v[0], 2), "s_v": np.round(v[1], 2), "t_v": np.round(v[2], 2),
            "r_a": np.round(a[0], 2), "s_a": np.round(a[1], 2), "t_a": np.round(a[2], 2),
            "status": np.int32(1),
        }
    )
    return frame[READING_COLUMNS]


def _write_context(
    connection: duckdb.DuckDBPyConnection,
    config: SimulationConfig,
    settings: FactorySettings,
    catalog: MeterCatalog,
    run_id: str,
) -> None:
    timeline = Timeline(config.start, config.days)
    plan = build_plan(timeline, settings, config.seed)
    calendar = pd.DataFrame(
        {
            "day": timeline.dates,
            "day_type": [kind.value for kind in plan.day_types],
            "overtime": plan.overtime,
            "holiday_name": [plan.holiday_names.get(day) for day in timeline.dates],
        }
    )
    weather = pd.DataFrame(
        {
            "ts": pd.DatetimeIndex(timeline.timestamps()),
            "temp_c": _temperature(config, catalog),
        }
    )
    connection.register("calendar_frame", calendar)
    connection.execute("INSERT INTO production_calendar SELECT * FROM calendar_frame")
    connection.register("weather_frame", weather)
    connection.execute("INSERT INTO weather_minute SELECT * FROM weather_frame")
    if config.scenarios:
        connection.executemany(
            "INSERT INTO scenarios VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (sc.id, sc.title, sc.caption or sc.title, sc.description, sc.replay.start,
                 sc.replay.end, json.dumps(sc.what_if))
                for sc in config.scenarios
            ],
        )
    connection.execute(
        "INSERT INTO simulation_runs VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, config.seed, config.start, config.days, SIMULATOR_VERSION,
         datetime.now(UTC).replace(tzinfo=None)),
    )


def _write_events(
    connection: duckdb.DuckDBPyConnection, events: list[GroundTruthEvent]
) -> None:
    if not events:
        return
    connection.executemany(
        "INSERT INTO ground_truth_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (e.event_id, e.scenario_id, e.event_type, list(e.meter_ids), e.start, e.end,
             e.severity, e.description)
            for e in events
        ],
    )


def run_simulation(
    connection: duckdb.DuckDBPyConnection,
    config: SimulationConfig,
    settings: FactorySettings,
    catalog: MeterCatalog,
    progress: Callable[[str, int, int], None] | None = None,
) -> SimulationSummary:
    """Simulate the plant and write readings, calendar, weather and run metadata to DuckDB."""
    began = time.perf_counter()
    run_id = uuid.uuid4().hex[:12]
    initialize_schema(connection)
    LocalRepository(connection).load_meter_master(catalog)
    _write_context(connection, config, settings, catalog, run_id)

    timeline = Timeline(config.start, config.days)
    timestamps = pd.DatetimeIndex(timeline.timestamps())
    feeder_ids = set(catalog.feeder_ids)
    plant_kw: FloatArray = np.zeros(timeline.minutes)
    total = len(catalog.feeders) + len(catalog.equipment)
    for done, (meter_id, series) in enumerate(simulate(config, settings, catalog), 1):
        if meter_id in feeder_ids:
            plant_kw += series.kw
        connection.register("reading_frame", _frame(meter_id, timestamps, series))
        connection.execute("INSERT INTO meter_reading_minute SELECT * FROM reading_frame")
        connection.unregister("reading_frame")
        if progress:
            progress(meter_id, done, total)

    interval = settings.demand.interval_minutes
    window_end = datetime.combine(timeline.start, datetime.min.time()) + timedelta(
        days=timeline.days
    )
    labelled = [
        e for e in build_effects(timeline, list(config.scenarios), catalog).events
        if e.end > datetime.combine(timeline.start, datetime.min.time()) and e.start < window_end
    ]
    exceedances = demand_exceedances(
        plant_kw, timeline, settings.demand.contract_capacity_kw, interval, labelled
    )
    _write_events(connection, labelled + exceedances)
    demand = plant_kw.reshape(-1, interval).mean(axis=1)
    peak = int(np.argmax(demand))
    night = (timeline.minute_of_day >= 120) & (timeline.minute_of_day < 240)
    return SimulationSummary(
        run_id=run_id,
        meters=total,
        rows=total * timeline.minutes,
        peak_demand_kw=float(demand[peak]),
        labelled_events=len(labelled),
        exceedance_intervals=len(exceedances),
        peak_demand_start=timestamps[peak * settings.demand.interval_minutes].to_pydatetime(),
        night_base_kw=float(np.median(plant_kw[night])),
        plant_mwh=float(plant_kw.sum() / 60.0 / 1000.0),
        elapsed_seconds=time.perf_counter() - began,
    )
