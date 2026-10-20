"""Derive power factor, phase voltages, phase currents and the kWh register from kW."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from factory_energy.simulator.timeline import FloatArray, RandomSource

NOMINAL_LINE_VOLTAGE = 380.0
UNMETERED_PF = 0.90
CAPACITOR_COMPENSATION = 0.55  # share of feeder reactive power cancelled by capacitor banks

BASE_PF: dict[str, float] = {
    "reflow_oven": 0.98,
    "smt_line": 0.90,
    "burn_in": 0.96,
    "wave_solder": 0.97,
    "test_bank": 0.93,
    "injection_molder": 0.86,
    "chiller": 0.88,
    "cooling_tower": 0.84,
    "air_compressor_fixed": 0.85,
    "air_compressor_vsd": 0.95,
    "air_dryer": 0.82,
    "server_room": 0.95,
    "ev_charger": 0.98,
}


@dataclass(frozen=True)
class ElectricalSeries:
    kw: FloatArray
    kvar: FloatArray
    pf: FloatArray
    voltages: tuple[FloatArray, FloatArray, FloatArray]
    currents: tuple[FloatArray, FloatArray, FloatArray]
    kwh: FloatArray


def equipment_pf(kw: FloatArray, rated_kw: float, category: str) -> FloatArray:
    """Motors and drives run at a worse power factor when lightly loaded."""
    load = np.clip(kw / rated_kw, 0.0, 1.0)
    return np.asarray(np.clip(BASE_PF.get(category, 0.9) - 0.12 * (1.0 - load) ** 2, 0.55, 0.99))


def reactive_kvar(kw: FloatArray, pf: FloatArray) -> FloatArray:
    return np.asarray(kw * np.tan(np.arccos(pf)))


def build_series(
    kw: FloatArray,
    kvar: FloatArray,
    rand: RandomSource,
    register_start: float,
) -> ElectricalSeries:
    kw = np.clip(kw, 0.0, None)
    apparent = np.hypot(kw, kvar)
    pf = np.where(apparent > 0.5, kw / np.maximum(apparent, 1e-9), np.nan)
    sag = 1.0 - 8e-6 * apparent  # ~0.4 % drop at 500 kVA
    line_v = NOMINAL_LINE_VOLTAGE * sag * rand.noise(0.002, smooth=10, tag="voltage")
    phase_offsets = rand.stream("phases").normal(0.0, 0.003, 3)
    voltages = tuple(np.asarray(line_v * (1.0 + offset)) for offset in phase_offsets)
    current = apparent * 1000.0 / (np.sqrt(3.0) * line_v)
    imbalance = rand.stream("imbalance").normal(0.0, 0.01, 3)
    imbalance -= imbalance.mean()
    currents = tuple(
        np.asarray(current * (1.0 + share) * rand.noise(0.003, smooth=1, tag=f"phase{index}"))
        for index, share in enumerate(imbalance)
    )
    energy = np.concatenate(([0.0], np.cumsum(kw[:-1]) / 60.0))
    return ElectricalSeries(
        kw=np.asarray(kw),
        kvar=np.asarray(kvar),
        pf=np.asarray(pf),
        voltages=(voltages[0], voltages[1], voltages[2]),
        currents=(currents[0], currents[1], currents[2]),
        kwh=np.asarray(register_start + energy),
    )
