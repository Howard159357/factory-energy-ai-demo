"""Per-category equipment load models (kW at one-minute resolution).

Each model is a small physical caricature of the real machine: reflow ovens preheat before the
line starts, molders draw a barrel-heating surge, chillers follow outdoor temperature and
production heat, fixed-speed compressors load/unload behind a VSD trim machine, and so on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property

import numpy as np

from factory_energy.config.models import EquipmentConfig
from factory_energy.simulator.schedule import DayType, ProductionPlan
from factory_energy.simulator.timeline import (
    EPOCH,
    MINUTES_PER_DAY,
    FloatArray,
    RandomSource,
    Timeline,
    delay_starts,
    extend,
    minutes_since_on,
)

REFLOW_PREHEAT_MIN = 45
REFLOW_LEAD_MAX_MIN = 60  # ovens switch on 35-60 min before the line starts
REFLOW_COOLDOWN_MIN = 30
WAVE_PREHEAT_MIN = 30
MOLDER_HEATUP_MIN = 40
CH1_MAX_SHARE = 0.9


@dataclass
class SimContext:
    timeline: Timeline
    plan: ProductionPlan
    temperature: FloatArray
    extra_air_demand_kw: FloatArray | None = None

    @cached_property
    def cooling_demand_kw(self) -> FloatArray:
        """Electrical kW the chiller plant must deliver (clean-room base + weather + process)."""
        weather = 11.0 * np.clip(self.temperature - 20.0, 0.0, None)
        # Condensers reject heat less efficiently on very hot days (chiller COP drops).
        derating = 1.0 + 0.05 * np.clip(self.temperature - 32.0, 0.0, None)
        return np.asarray((15.0 + weather + 90.0 * self.plan.plant_activity) * derating)

    @cached_property
    def chiller_split(self) -> tuple[FloatArray, FloatArray]:
        demand = self.cooling_demand_kw
        ch1 = np.minimum(demand, 200.0 * CH1_MAX_SHARE)
        rest = demand - ch1
        ch2 = np.where(rest > 15.0, np.clip(rest, 60.0, 240.0), 0.0)
        return np.asarray(ch1), np.asarray(ch2)

    @cached_property
    def air_demand_kw(self) -> FloatArray:
        """Compressed-air demand expressed as compressor shaft kW."""
        plan = self.plan
        activity = 0.3 * plan.smt_activity + 0.5 * plan.molding_activity
        activity = activity + 0.2 * plan.assembly_activity
        extra = 0.0 if self.extra_air_demand_kw is None else self.extra_air_demand_kw
        # Hot intake air makes compressors work harder for the same flow.
        intake = 1.0 + 0.01 * np.clip(self.temperature - 30.0, 0.0, None)
        return np.asarray((35.0 + 120.0 * activity + extra) * intake)

    @cached_property
    def compressor_split(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        """AC-01 base load, AC-03 VSD trim, AC-02 lead-lag (fixed speed)."""
        demand = self.air_demand_kw
        base_share = np.clip(demand / 70.0, 0.0, 1.0)
        ac1 = 75.0 * (0.33 + 0.67 * base_share)
        trim = np.clip(demand - 70.0, 0.0, None)
        ac3 = np.where(trim > 0, 5.0 + np.minimum(trim, 50.0), 3.0)
        lag = np.clip(trim - 50.0, 0.0, None)
        ac2 = np.where(lag > 0, 75.0 * (0.33 + 0.67 * np.clip(lag / 70.0, 0.0, 1.0)), 0.0)
        return np.asarray(ac1), np.asarray(ac2), np.asarray(ac3)


Model = Callable[[SimContext, EquipmentConfig, RandomSource], FloatArray]


def _line_for(spec: EquipmentConfig) -> str:
    return f"SMT-L{int(spec.meter_id.split('-')[1])}"


def reflow_oven(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    line = ctx.plan.running[_line_for(spec)]
    on = extend(line, before=REFLOW_LEAD_MAX_MIN, after=REFLOW_COOLDOWN_MIN)
    spread = REFLOW_LEAD_MAX_MIN - 35
    on = delay_starts(on, lambda m: int(rand.day_of(m, "preheat").integers(0, spread + 1)))
    heating = minutes_since_on(on) < REFLOW_PREHEAT_MIN
    level = np.where(heating, 0.80, np.where(line, 0.44, 0.36))
    level = np.where(on, level, 0.0)
    return np.asarray(spec.rated_kw * level * rand.noise(0.02))


def smt_line(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    running = ctx.plan.running[spec.meter_id]
    # Lines take staggered lunch breaks: L1 at 11:45, L2 at 12:00, L3 at 12:15.
    lunch = np.roll(ctx.plan.lunch, 15 * (int(spec.meter_id[-1]) - 2))
    level = np.where(running, np.where(lunch, 0.30, 0.72), 0.04)
    return np.asarray(spec.rated_kw * level * rand.noise(0.04))


def burn_in(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    """Back-to-back burn-in batches of 24-48 h with loading/unloading gaps."""
    timeline = ctx.timeline
    offset = (timeline.start - EPOCH).days * MINUTES_PER_DAY
    if offset < 0:
        raise ValueError(f"simulation must start on or after {EPOCH}")
    # Batches are drawn from a fixed epoch so any window sees the same batch history.
    level = np.full(offset + timeline.minutes, 0.08)
    rng = rand.stream("batches")
    cursor = int(rng.integers(0, 12 * 60))
    while cursor < level.size:
        duration = int(rng.integers(24 * 60, 48 * 60))
        ramp = 120
        end = min(cursor + duration, level.size)
        level[cursor:end] = 0.85 * rng.uniform(0.85, 1.0)
        level[cursor:min(cursor + ramp, end)] = 0.45
        level[max(end - 60, cursor):end] = 0.40
        cursor = end + int(rng.integers(2 * 60, 6 * 60))
    level = level[offset:]
    return np.asarray(spec.rated_kw * level * rand.noise(0.015))


def wave_solder(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    running = ctx.plan.running[spec.meter_id]
    on = extend(running, before=WAVE_PREHEAT_MIN)
    heating = minutes_since_on(on) < WAVE_PREHEAT_MIN
    level = np.where(heating, 0.90, np.where(ctx.plan.lunch, 0.45, 0.55))
    level = np.where(on, level, 0.03)
    return np.asarray(spec.rated_kw * level * rand.noise(0.03))


def ict_fct_bank(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    level = 0.15 + 0.60 * ctx.plan.smt_activity
    return np.asarray(spec.rated_kw * level * rand.noise(0.05))


def injection_molder(
    ctx: SimContext, spec: EquipmentConfig, rand: RandomSource
) -> FloatArray:
    running = ctx.plan.running[spec.meter_id]
    heating = minutes_since_on(running) < MOLDER_HEATUP_MIN
    level = np.where(running, np.where(heating, 0.78, 0.53), 0.03)
    return np.asarray(spec.rated_kw * level * rand.noise(0.05, smooth=2))


def chiller(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    ch1, ch2 = ctx.chiller_split
    load = ch1 if spec.meter_id.endswith("01") else ch2
    return np.asarray(load * rand.noise(0.02, smooth=15))


def cooling_tower(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    ch1, ch2 = ctx.chiller_split
    humid_heat = np.clip((ctx.temperature - 18.0) / 16.0, 0.0, 1.0)
    level = 0.10 + 0.40 * (ch1 + ch2) / 400.0 + 0.15 * humid_heat
    return np.asarray(spec.rated_kw * level * rand.noise(0.02, smooth=15))


def air_compressor_fixed(
    ctx: SimContext, spec: EquipmentConfig, rand: RandomSource
) -> FloatArray:
    ac1, ac2, _ = ctx.compressor_split
    load = ac1 if spec.meter_id.endswith("01") else ac2
    return np.asarray(load * spec.rated_kw / 75.0 * rand.noise(0.03, smooth=3))


def air_compressor_vsd(
    ctx: SimContext, spec: EquipmentConfig, rand: RandomSource
) -> FloatArray:
    _, _, ac3 = ctx.compressor_split
    return np.asarray(ac3 * rand.noise(0.04, smooth=3))


def air_dryer(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    airflow = np.clip(ctx.air_demand_kw / 155.0, 0.0, 1.0)
    level = 0.30 + 0.45 * airflow + 0.15 * np.clip((ctx.temperature - 15.0) / 20.0, 0.0, 1.0)
    return np.asarray(spec.rated_kw * level * rand.noise(0.02))


def server_room(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    level = 0.82 + 0.06 * np.clip((ctx.temperature - 20.0) / 15.0, 0.0, 1.0)
    return np.asarray(spec.rated_kw * level * rand.noise(0.01, smooth=30))


def ev_charger(ctx: SimContext, spec: EquipmentConfig, rand: RandomSource) -> FloatArray:
    """Commuter EV charging: arrivals 07:30-09:30 on workdays, a few on Saturdays."""
    chargers = 4
    per_charger = spec.rated_kw / chargers
    load = np.zeros(ctx.timeline.minutes)
    for offset, (day, kind) in enumerate(zip(ctx.timeline.dates, ctx.plan.day_types, strict=True)):
        rng = rand.day(day, "sessions")
        sessions = {DayType.WORKDAY: chargers, DayType.SATURDAY: int(rng.integers(0, 2))}.get(
            kind, 0
        )
        for _ in range(sessions):
            if rng.random() < 0.15:
                continue
            start = offset * MINUTES_PER_DAY + int(rng.integers(450, 570))
            end = min(start + int(rng.integers(60, 240)), load.size)
            load[start:end] += per_charger * rng.uniform(0.92, 1.0)
    return load


MODELS: dict[str, Model] = {
    "reflow_oven": reflow_oven,
    "smt_line": smt_line,
    "burn_in": burn_in,
    "wave_solder": wave_solder,
    "test_bank": ict_fct_bank,
    "injection_molder": injection_molder,
    "chiller": chiller,
    "cooling_tower": cooling_tower,
    "air_compressor_fixed": air_compressor_fixed,
    "air_compressor_vsd": air_compressor_vsd,
    "air_dryer": air_dryer,
    "server_room": server_room,
    "ev_charger": ev_charger,
}


def unmetered_load(ctx: SimContext, feeder_id: str, rand: RandomSource) -> FloatArray:
    """Loads on each feeder that have no sub-meter (lighting, AOI, AHU fans, office, ...)."""
    plan = ctx.plan
    warm = np.clip((ctx.temperature - 24.0) / 10.0, 0.0, 1.0)
    profiles: dict[str, FloatArray] = {
        "MDB-1": 6.0 + 18.0 * plan.smt_activity,
        "MDB-2": 8.0 + 20.0 * plan.assembly_activity,
        "MDB-3": 6.0 + 30.0 * plan.molding_activity,
        "MDB-4": 25.0 + 20.0 * plan.plant_activity,
        "MDB-5": np.full(ctx.timeline.minutes, 2.0),
        "MDB-6": 12.0 + 40.0 * plan.office + 10.0 * warm * plan.office,
    }
    base = profiles.get(feeder_id, np.zeros(ctx.timeline.minutes))
    return np.asarray(base * rand.noise(0.03))
