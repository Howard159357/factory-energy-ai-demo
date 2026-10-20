"""Scenario engine: YAML-described incidents injected into the simulation with ground truth.

Each event type changes the simulation at the level where it physically happens:

- ``heat_wave`` raises outdoor temperature before any equipment model runs.
- ``air_leak`` adds compressed-air demand, so the compressor split and dryer react naturally.
- ``capacitor_fault`` removes reactive compensation on one feeder (power factor drops).
- ``simultaneous_start`` and ``left_running`` override one meter's kW profile in a time window.

Every event also yields a labelled ``GroundTruthEvent`` used later to score anomaly detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from factory_energy.config.models import EquipmentConfig, MeterCatalog
from factory_energy.simulator.electrical import CAPACITOR_COMPENSATION
from factory_energy.simulator.timeline import FloatArray, Timeline, noise, rng_for

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "config" / "scenarios"
PRE_START_OFF_MIN = 180

# category -> (level while off, level while starting up, start-up minutes), as share of rating
STARTUP_PROFILES: dict[str, tuple[float, float, int]] = {
    "injection_molder": (0.03, 0.95, 40),  # cold barrels: every heater band on
    "reflow_oven": (0.0, 0.95, 45),  # cold oven: all zones heating
    "wave_solder": (0.03, 0.95, 30),
    "chiller": (0.0, 0.45, 30),
    "air_compressor_fixed": (0.0, 1.0, 20),
}
# Machines that keep running after a manual start even when the plant does not need them yet:
# category -> (level while held, minutes). Scheduled machines simply follow their schedule.
HOLD_AFTER_START: dict[str, tuple[float, int]] = {
    "chiller": (0.30, 150),  # staged in by hand, unloaded to its minimum until mid-morning
}


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SimultaneousStart(_Event):
    type: Literal["simultaneous_start"]
    at: datetime
    meters: tuple[str, ...] = Field(min_length=2)
    stagger_minutes: int = Field(default=0, ge=0, le=60)  # 0 = all at once (the incident)


class HeatWave(_Event):
    type: Literal["heat_wave"]
    start: date
    days: int = Field(gt=0, le=14)
    peak_delta_c: float = Field(gt=0, le=10)


class AirLeak(_Event):
    type: Literal["air_leak"]
    start: datetime
    full_at: datetime
    repaired_at: datetime
    max_kw: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> AirLeak:
        if not self.start < self.full_at <= self.repaired_at:
            raise ValueError("air_leak needs start < full_at <= repaired_at")
        return self


class LeftRunning(_Event):
    type: Literal["left_running"]
    meter: str
    start: datetime
    end: datetime
    level: float = Field(gt=0, le=1)


class CapacitorFault(_Event):
    type: Literal["capacitor_fault"]
    feeder: str
    start: datetime
    end: datetime
    compensation: float = Field(ge=0, lt=CAPACITOR_COMPENSATION)


Event = Annotated[
    SimultaneousStart | HeatWave | AirLeak | LeftRunning | CapacitorFault,
    Field(discriminator="type"),
]


class ReplayWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: datetime
    end: datetime


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^S\d{1,2}$")
    title: str
    caption: str = Field(default="", max_length=90)  # one line shown in the replay clock bar
    description: str
    replay: ReplayWindow
    events: tuple[Event, ...] = ()
    what_if: dict[str, float] = Field(default_factory=dict)


@dataclass(frozen=True)
class GroundTruthEvent:
    event_id: str
    scenario_id: str
    event_type: str
    meter_ids: tuple[str, ...]
    start: datetime
    end: datetime
    severity: str
    description: str


def load_scenarios(directory: Path = SCENARIO_DIR) -> list[Scenario]:
    scenarios = []
    for path in sorted(directory.glob("*.yaml")):
        with path.open(encoding="utf-8") as handle:
            scenarios.append(Scenario.model_validate(yaml.safe_load(handle)))
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario id")
    return scenarios


@dataclass(frozen=True)
class _Override:
    meter: str
    start: int
    end: int
    levels: FloatArray  # share of rating, one value per minute in [start, end)
    only_raise: bool  # keep the original value where it is already higher


@dataclass
class ScenarioEffects:
    """All scenario changes for one timeline, ready to apply inside the simulator."""

    timeline: Timeline
    temperature_delta: FloatArray
    air_demand_delta: FloatArray
    compensation: dict[str, FloatArray] = field(default_factory=dict)
    overrides: list[_Override] = field(default_factory=list)
    events: list[GroundTruthEvent] = field(default_factory=list)

    def minute(self, ts: datetime) -> int:
        origin = datetime.combine(self.timeline.start, datetime.min.time())
        return int((ts - origin).total_seconds() // 60)

    def feeder_compensation(self, feeder_id: str) -> FloatArray:
        return self.compensation.get(
            feeder_id, np.full(self.timeline.minutes, CAPACITOR_COMPENSATION)
        )

    def apply(self, spec: EquipmentConfig, kw: FloatArray, seed: int) -> FloatArray:
        result = kw.copy()
        for index, item in enumerate(o for o in self.overrides if o.meter == spec.meter_id):
            lo, hi = max(item.start, 0), min(item.end, result.size)
            if lo >= hi:
                continue
            levels = item.levels[lo - item.start:hi - item.start]
            rng = rng_for(seed, spec.meter_id, "scenario", str(index))
            full = noise(rng, item.levels.size, 0.02)
            jitter = full[lo - item.start:hi - item.start]
            new = spec.rated_kw * levels * jitter
            result[lo:hi] = np.maximum(result[lo:hi], new) if item.only_raise else new
        return result


def _span(effects: ScenarioEffects, start: datetime, end: datetime) -> tuple[int, int]:
    return effects.minute(start), effects.minute(end)


def _add_simultaneous_start(
    effects: ScenarioEffects, scenario: Scenario, event: SimultaneousStart,
    catalog: dict[str, EquipmentConfig],
) -> None:
    t0 = effects.minute(event.at)
    longest = 0
    for order, meter in enumerate(event.meters):
        off, start_level, minutes = STARTUP_PROFILES[catalog[meter].category]
        start = t0 + order * event.stagger_minutes
        waiting = start - (t0 - PRE_START_OFF_MIN)
        levels = np.concatenate((np.full(waiting, off), np.full(minutes, start_level)))
        effects.overrides.append(
            _Override(meter, t0 - PRE_START_OFF_MIN, start + minutes, levels, only_raise=False)
        )
        hold = HOLD_AFTER_START.get(catalog[meter].category)
        if hold is not None:
            level, held = hold
            effects.overrides.append(_Override(
                meter, start + minutes, start + minutes + held, np.full(held, level),
                only_raise=True,
            ))
        longest = max(longest, start - t0 + minutes)
    effects.events.append(GroundTruthEvent(
        f"{scenario.id}-SIMULTANEOUS_START", scenario.id, "SIMULTANEOUS_START", event.meters,
        event.at, event.at + timedelta(minutes=longest), "high",
        f"{len(event.meters)} machines started within the same minute",
    ))


def _add_heat_wave(effects: ScenarioEffects, scenario: Scenario, event: HeatWave) -> None:
    start = datetime.combine(event.start, datetime.min.time())
    lo, hi = _span(effects, start, start + timedelta(days=event.days))
    minutes = np.arange(hi - lo)
    envelope = np.sin(np.pi * (minutes + 0.5) / (hi - lo)) ** 0.5
    hour = (minutes % 1440) / 60.0
    diurnal = 0.55 + 0.45 * np.cos(2 * np.pi * (hour - 14.5) / 24)
    delta = event.peak_delta_c * envelope * diurnal
    a, b = max(lo, 0), min(hi, effects.timeline.minutes)
    if a < b:
        effects.temperature_delta[a:b] += delta[a - lo:b - lo]
    effects.events.append(GroundTruthEvent(
        f"{scenario.id}-HEAT_WAVE", scenario.id, "HEAT_WAVE", ("CH-01", "CH-02", "MDB-4"),
        start, start + timedelta(days=event.days), "medium",
        f"Heat wave, up to +{event.peak_delta_c:.1f} °C above normal",
    ))


def _add_air_leak(effects: ScenarioEffects, scenario: Scenario, event: AirLeak) -> None:
    lo, full = _span(effects, event.start, event.full_at)
    hi = effects.minute(event.repaired_at)
    ramp = np.linspace(0.0, event.max_kw, full - lo, endpoint=False)
    profile = np.concatenate((ramp, np.full(hi - full, event.max_kw)))
    a, b = max(lo, 0), min(hi, effects.timeline.minutes)
    if a < b:
        effects.air_demand_delta[a:b] += profile[a - lo:b - lo]
    effects.events.append(GroundTruthEvent(
        f"{scenario.id}-AIR_LEAK", scenario.id, "AIR_LEAK",
        ("AC-01", "AC-02", "AC-03", "MDB-5"), event.start, event.repaired_at, "medium",
        f"Compressed-air leak growing to {event.max_kw:.0f} kW until repaired",
    ))


def _add_left_running(effects: ScenarioEffects, scenario: Scenario, event: LeftRunning) -> None:
    lo, hi = _span(effects, event.start, event.end)
    effects.overrides.append(
        _Override(event.meter, lo, hi, np.full(hi - lo, event.level), only_raise=True)
    )
    effects.events.append(GroundTruthEvent(
        f"{scenario.id}-OFF_SCHEDULE_RUNNING", scenario.id, "OFF_SCHEDULE_RUNNING",
        (event.meter,), event.start, event.end, "medium",
        f"{event.meter} left running outside the production schedule",
    ))


def _add_capacitor_fault(
    effects: ScenarioEffects, scenario: Scenario, event: CapacitorFault
) -> None:
    lo, hi = _span(effects, event.start, event.end)
    values = effects.feeder_compensation(event.feeder).copy()
    values[max(lo, 0):min(hi, values.size)] = event.compensation
    effects.compensation[event.feeder] = values
    effects.events.append(GroundTruthEvent(
        f"{scenario.id}-LOW_POWER_FACTOR", scenario.id, "LOW_POWER_FACTOR", (event.feeder,),
        event.start, event.end, "medium",
        f"Capacitor bank fault on {event.feeder}; power factor drops",
    ))


def build_effects(
    timeline: Timeline, scenarios: list[Scenario], catalog: MeterCatalog
) -> ScenarioEffects:
    effects = ScenarioEffects(
        timeline, np.zeros(timeline.minutes), np.zeros(timeline.minutes)
    )
    equipment = {e.meter_id: e for e in catalog.equipment}
    feeders = set(catalog.feeder_ids)
    for scenario in scenarios:
        for event in scenario.events:
            if isinstance(event, SimultaneousStart):
                unknown = set(event.meters) - set(equipment)
                if unknown:
                    raise ValueError(f"{scenario.id}: unknown meters {sorted(unknown)}")
                _add_simultaneous_start(effects, scenario, event, equipment)
            elif isinstance(event, HeatWave):
                _add_heat_wave(effects, scenario, event)
            elif isinstance(event, AirLeak):
                _add_air_leak(effects, scenario, event)
            elif isinstance(event, LeftRunning):
                if event.meter not in equipment:
                    raise ValueError(f"{scenario.id}: unknown meter {event.meter}")
                _add_left_running(effects, scenario, event)
            elif event.feeder in feeders:
                _add_capacitor_fault(effects, scenario, event)
            else:
                raise ValueError(f"{scenario.id}: unknown feeder {event.feeder}")
    return effects


def demand_exceedances(
    plant_kw: FloatArray,
    timeline: Timeline,
    contract_kw: float,
    interval: int,
    labelled: list[GroundTruthEvent],
) -> list[GroundTruthEvent]:
    """Label every demand interval above the contract, attributed to the overlapping scenario."""
    demand = plant_kw.reshape(-1, interval).mean(axis=1)
    origin = datetime.combine(timeline.start, datetime.min.time())
    found = []
    for index in np.flatnonzero(demand > contract_kw):
        start = origin + timedelta(minutes=int(index) * interval)
        end = start + timedelta(minutes=interval)
        owner = next((e.scenario_id for e in labelled if e.start < end and start < e.end), "BASE")
        found.append(GroundTruthEvent(
            f"{owner}-DEMAND_EXCEEDANCE-{start:%Y%m%d%H%M}", owner, "DEMAND_EXCEEDANCE",
            ("PLANT",), start, end, "high",
            f"15-min demand {demand[index]:,.0f} kW above contract {contract_kw:,.0f} kW",
        ))
    return found
