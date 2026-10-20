from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property

import pandas as pd

from factory_energy.anomaly.evaluate import Score
from factory_energy.config.models import FactorySettings, MeterCatalog
from factory_energy.dashboard.data import DashboardData, ScenarioInfo
from factory_energy.dashboard.status import TickState, compute
from factory_energy.forecasting.backtest import HorizonMetrics, PeakMetrics
from factory_energy.simulator.scenarios import Scenario, load_scenarios
from factory_energy.simulator.whatif import StaggerResult, staggered_start

TICK_CACHE = 16


@dataclass
class Context:
    """Everything a page needs, with expensive whole-run summaries computed once."""

    data: DashboardData
    settings: FactorySettings
    catalog: MeterCatalog
    _whatif: dict[str, StaggerResult | None] = field(default_factory=dict)
    _ticks: OrderedDict[datetime, TickState] = field(default_factory=OrderedDict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def contract_kw(self) -> float:
        return self.settings.demand.contract_capacity_kw

    @property
    def warning_kw(self) -> float:
        return self.contract_kw * self.settings.demand.warning_ratio

    @cached_property
    def scenarios(self) -> dict[str, ScenarioInfo]:
        return {s.scenario_id: s for s in self.data.scenarios()}

    @cached_property
    def scenario_definitions(self) -> dict[str, Scenario]:
        return {s.id: s for s in load_scenarios()}

    @cached_property
    def forecast_metrics(self) -> list[HorizonMetrics]:
        return self.data.forecast_metrics()

    @cached_property
    def detection_scores(self) -> list[Score]:
        return self.data.detection_scores()

    @cached_property
    def peak_metrics(self) -> list[PeakMetrics]:
        return self.data.peak_metrics()

    @cached_property
    def alert_leads(self) -> dict[str, list[str]]:
        """Per model, the alarm lead (minutes) for each real exceedance episode."""
        return self.data.alert_leads()

    @cached_property
    def weekday_hour(self) -> pd.DataFrame:
        return self.data.weekday_hour_profile()

    @cached_property
    def monthly_energy(self) -> pd.DataFrame:
        return self.data.monthly_energy()

    def tick(self, now: datetime) -> TickState:
        """State of the plant at `now`, shared by every callback of the same tick."""
        with self._lock:
            state = self._ticks.get(now)
            if state is None:
                state = compute(self, now)
                self._ticks[now] = state
                while len(self._ticks) > TICK_CACHE:
                    self._ticks.popitem(last=False)
            return state

    def whatif(self, scenario_id: str) -> StaggerResult | None:
        with self._lock:
            if scenario_id not in self._whatif:
                definition = self.scenario_definitions.get(scenario_id)
                self._whatif[scenario_id] = None if definition is None else staggered_start(
                    definition, self.settings, self.catalog, seed=self.data.seed
                )
            return self._whatif[scenario_id]

    def precompute(self) -> None:
        """Run the what-ifs up front so the first visit to the Demand page is instant."""
        for scenario_id in self.scenarios:
            self.whatif(scenario_id)

    def default_scenario(self) -> str | None:
        """Open on the simultaneous start if it exists: it is the most visual incident."""
        if "S2" in self.scenarios:
            return "S2"
        return next(iter(self.scenarios), None)

    def replay_window(self, scenario_id: str | None) -> tuple[datetime, datetime]:
        info = self.scenarios.get(scenario_id) if scenario_id else None
        first, last = self.data.first_ts, self.data.last_ts
        if info is not None:
            start, end = max(info.replay_start, first), min(info.replay_end, last)
            if start < end:
                return start, end
        start = min(first + timedelta(days=7), last - timedelta(days=1))
        return start, min(start + timedelta(days=7), last)
