"""Counterfactuals: re-simulate an incident day with a different operating decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from factory_energy.config.models import FactorySettings, MeterCatalog
from factory_energy.simulator.generator import SimulationConfig, simulate
from factory_energy.simulator.scenarios import Scenario, SimultaneousStart
from factory_energy.simulator.timeline import FloatArray


@dataclass(frozen=True)
class StaggerResult:
    day: date
    stagger_minutes: int
    actual_kw: FloatArray  # plant kW per minute as it happened
    staggered_kw: FloatArray  # plant kW per minute with a staggered start-up
    actual_peak_kw: float  # highest 15-minute demand
    staggered_peak_kw: float

    @property
    def reduction_kw(self) -> float:
        return self.actual_peak_kw - self.staggered_peak_kw


def _plant(
    day: date, scenario: Scenario, settings: FactorySettings, catalog: MeterCatalog, seed: int
) -> FloatArray:
    config = SimulationConfig(day, 1, seed, (scenario,))
    feeders = set(catalog.feeder_ids)
    return np.sum([s.kw for meter, s in simulate(config, settings, catalog) if meter in feeders],
                  axis=0)


def staggered_start(
    scenario: Scenario, settings: FactorySettings, catalog: MeterCatalog, seed: int = 42,
    stagger_minutes: int | None = None,
) -> StaggerResult | None:
    """Replay a simultaneous-start scenario with machines started one after another."""
    event = next((e for e in scenario.events if isinstance(e, SimultaneousStart)), None)
    if event is None:
        return None
    step = int(stagger_minutes or scenario.what_if.get("stagger_minutes", 15))
    alternative = scenario.model_copy(
        update={"events": (event.model_copy(update={"stagger_minutes": step}),)}
    )
    day = event.at.date()
    actual = _plant(day, scenario, settings, catalog, seed)
    staggered = _plant(day, alternative, settings, catalog, seed)
    interval = settings.demand.interval_minutes

    def peak(kw: FloatArray) -> float:
        return float(kw.reshape(-1, interval).mean(axis=1).max())

    return StaggerResult(day, step, actual, staggered, peak(actual), peak(staggered))
