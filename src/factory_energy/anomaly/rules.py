"""Layer 1: explainable rules an energy engineer would write down."""

from __future__ import annotations

import numpy as np
import pandas as pd

from factory_energy.anomaly.data import PlantData, runs
from factory_energy.anomaly.models import Detection, Layer

# Machines whose start-up draws a surge worth coordinating.
STARTING_CATEGORIES = frozenset({
    "reflow_oven", "injection_molder", "wave_solder", "chiller", "air_compressor_fixed",
})
# Production machines that should follow the production schedule.
SCHEDULED_CATEGORIES = frozenset({
    "reflow_oven", "smt_line", "injection_molder", "wave_solder",
})


def _ts(data: PlantData, index: int) -> pd.Timestamp:
    return data.kw.index[min(index, len(data.kw.index) - 1)]


def machine_starts(data: PlantData, meter_id: str) -> list[int]:
    """Minute indexes where a machine goes from (near) off to running."""
    rated = data.rated(meter_id)
    kw = data.kw[meter_id].to_numpy()
    before = pd.Series(kw).rolling(15, min_periods=15).mean().shift(1).to_numpy()
    after = pd.Series(kw[::-1]).rolling(5, min_periods=5).mean().to_numpy()[::-1]
    start = (before < 0.15 * rated) & (after > 0.40 * rated)
    edges = np.flatnonzero(start & ~np.concatenate(([False], start[:-1])))
    return [int(i) for i in edges]


def simultaneous_starts(
    data: PlantData, min_machines: int = 6, window_min: int = 3
) -> list[Detection]:
    """Several high-power machines starting within a few minutes of each other."""
    starts = sorted(
        (index, meter)
        for meter in data.equipment_ids
        if data.category(meter) in STARTING_CATEGORIES
        for index in machine_starts(data, meter)
    )
    detections: list[Detection] = []
    cluster: list[tuple[int, str]] = []

    def flush() -> None:
        meters = tuple(sorted({m for _, m in cluster}))
        if len(meters) >= min_machines:
            first = cluster[0][0]
            surge = sum(data.rated(m) for m in meters)
            detections.append(Detection(
                Layer.RULE, "rule:simultaneous_start", "SIMULTANEOUS_START", meters,
                _ts(data, first).to_pydatetime(), _ts(data, first + 30).to_pydatetime(),
                "high", float(len(meters)),
                f"{len(meters)} machines ({surge:,.0f} kW rated) started within "
                f"{window_min} min; stagger the start-up to cut the demand peak",
                _ts(data, first + window_min + 5).to_pydatetime(),
            ))

    for index, meter in starts:
        if cluster and index - cluster[0][0] > window_min:
            flush()
            cluster = []
        cluster.append((index, meter))
    if cluster:
        flush()
    return detections


def _usual_share(on: pd.Series, day_type: pd.Series, hour: pd.Index) -> pd.Series:
    """How often the machine runs at this hour on other days of the same type.

    Leave-one-day-out, so a single long incident does not teach the detector that it is normal.
    """
    per_day = on.groupby([on.index.date, day_type, hour]).mean()
    keys = per_day.index.droplevel(0)
    totals = per_day.groupby(level=[1, 2]).transform("sum")
    counts = per_day.groupby(level=[1, 2]).transform("count")
    others = ((totals - per_day) / (counts - 1)).where(counts > 1, 1.0)
    lookup = pd.Series(others.to_numpy(), index=pd.MultiIndex.from_arrays(
        [per_day.index.get_level_values(0), keys.get_level_values(0), keys.get_level_values(1)]
    ))
    index = pd.MultiIndex.from_arrays([on.index.date, day_type.to_numpy(), hour])
    return pd.Series(lookup.reindex(index).to_numpy(), index=on.index)


def off_schedule_running(
    data: PlantData, min_minutes: int = 120, rarity: float = 0.05
) -> list[Detection]:
    """Production equipment running at an hour/day type where it practically never runs."""
    hour = data.kw.index.hour
    detections: list[Detection] = []
    for meter in data.equipment_ids:
        if data.category(meter) not in SCHEDULED_CATEGORIES:
            continue
        on = data.kw[meter] > 0.2 * data.rated(meter)
        unusual = on & (_usual_share(on, data.day_type, hour) < rarity)
        for lo, hi in runs(unusual, min_minutes, max_gap=10):
            kwh = float(data.kw[meter].iloc[lo:hi].sum() / 60)
            detections.append(Detection(
                Layer.RULE, "rule:off_schedule", "OFF_SCHEDULE_RUNNING", (meter,),
                _ts(data, lo).to_pydatetime(), _ts(data, hi).to_pydatetime(),
                "medium", kwh,
                f"{meter} ran {(hi - lo) / 60:.1f} h outside its normal schedule "
                f"({kwh:,.0f} kWh)",
                _ts(data, lo + min_minutes).to_pydatetime(),
            ))
    return detections


def low_power_factor(
    data: PlantData, threshold: float = 0.90, min_minutes: int = 60
) -> list[Detection]:
    """Feeder power factor below threshold while the feeder carries meaningful load."""
    detections: list[Detection] = []
    for feeder in data.feeder_ids:
        pf = data.pf[feeder].rolling(15, min_periods=10).mean()
        loaded = data.kw[feeder] > 0.10 * data.rated(feeder)
        for lo, hi in runs((pf < threshold) & loaded, min_minutes, max_gap=60):
            worst = float(pf.iloc[lo:hi].min())
            detections.append(Detection(
                Layer.RULE, "rule:low_pf", "LOW_POWER_FACTOR", (feeder,),
                _ts(data, lo).to_pydatetime(), _ts(data, hi).to_pydatetime(),
                "medium", worst,
                f"{feeder} power factor down to {worst:.2f} (threshold {threshold:.2f}); "
                "check the capacitor bank",
                _ts(data, lo + min_minutes).to_pydatetime(),
            ))
    return detections


def demand_exceedance(data: PlantData) -> list[Detection]:
    """15-minute demand intervals above the contract capacity."""
    interval = f"{data.interval_minutes}min"
    demand = data.plant_kw.resample(interval).mean()
    detections = []
    for start, value in demand[demand > data.contract_kw].items():
        stamp = pd.Timestamp(start)
        detections.append(Detection(
            Layer.RULE, "rule:demand", "DEMAND_EXCEEDANCE", ("PLANT",),
            stamp.to_pydatetime(),
            (stamp + pd.Timedelta(minutes=data.interval_minutes)).to_pydatetime(),
            "high", float(value),
            f"15-min demand {value:,.0f} kW above contract {data.contract_kw:,.0f} kW",
            (stamp + pd.Timedelta(minutes=data.interval_minutes)).to_pydatetime(),
        ))
    return detections


def run_rules(data: PlantData) -> list[Detection]:
    return [
        *simultaneous_starts(data),
        *off_schedule_running(data),
        *low_power_factor(data),
        *demand_exceedance(data),
    ]
