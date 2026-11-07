"""Everything the pages need about one replay instant, computed once per tick.

Several callbacks fire on every tick (the status banner plus the current page). They all
read the same ``TickState`` so each query runs once per instant, not once per widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from factory_energy.dashboard.data import INTERVAL, interval_floor
from factory_energy.energy.demand import running_interval
from factory_energy.energy.tariff import energy_cost, exceedance_penalty, money

if TYPE_CHECKING:
    from factory_energy.dashboard.context import Context

WARNING_PROBABILITY = 0.2
ALARM_PROBABILITY = 0.5
INTERVAL_MINUTES = 15


class Level(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    ALARM = "ALARM"

    @property
    def tone(self) -> str:
        return {Level.OK: "ok", Level.WARNING: "warn", Level.ALARM: "bad"}[self]


@dataclass(frozen=True)
class TickState:
    now: datetime
    contract_kw: float
    snapshot: pd.DataFrame  # kw, pf per meter (NaN where no reading)
    plant_kw: float
    interval_start: datetime
    elapsed_min: int
    so_far_kw: float
    projected_kw: float
    forecast: pd.DataFrame  # next-hour forecasts issued at the last completed interval
    p_exceed: float  # the highest chance over the next-hour intervals
    p_exceed_at: datetime | None  # start of the interval that chance is for
    peak_3h_kw: float | None  # highest P50 over the next 3 hours
    peak_3h_at: datetime | None
    detections_24h: pd.DataFrame
    energy_today_kwh: float
    cost_today: float
    temperature: float | None
    level: Level
    headline: str
    action: str

    @property
    def contract_ratio(self) -> float:
        return self.projected_kw / max(self.contract_kw, 1.0)

    @property
    def interval_end(self) -> datetime:
        return self.interval_start + INTERVAL

    @property
    def risk_interval(self) -> str:
        """The interval the next-hour chance is for, e.g. "08:15-08:30" (empty without one)."""
        return "" if self.p_exceed_at is None else _interval(self.p_exceed_at)

    @property
    def forecast_level(self) -> Level:
        if self.p_exceed >= ALARM_PROBABILITY:
            return Level.ALARM
        return Level.WARNING if self.p_exceed >= WARNING_PROBABILITY else Level.OK


def projection(series: pd.DataFrame, minutes: int = INTERVAL_MINUTES) -> tuple[int, float, float]:
    """Demand-controller view of the running interval: (elapsed, average so far, projected)."""
    return running_interval([float(kw) for kw in series.kw], minutes)


def compute(ctx: Context, now: datetime) -> TickState:
    data, contract, tariff = ctx.data, ctx.contract_kw, ctx.settings.tariff
    # The latest complete minute: the one the projection holds to the end of the interval,
    # and the "present load" get_equipment_status reports (the minute stamped `now` has
    # only just begun).
    snapshot = data.snapshot(now - timedelta(minutes=1))
    plant_kw = float(snapshot.kw.reindex(data.feeder_ids).fillna(0.0).sum())
    start = interval_floor(now)
    elapsed, so_far, projected = projection(data.plant_series(start, now))
    if elapsed == 0:  # first minute of an interval: the present load is the best estimate
        so_far = projected = plant_kw
    ahead = data.next_forecast(now, 180)
    forecast = ahead[ahead.horizon_min <= 60]
    p_exceed = float(forecast.p_exceed.max()) if len(forecast) else 0.0
    p_exceed_at = (pd.Timestamp(forecast.loc[forecast.p_exceed.idxmax(), "target_ts"])
                   .to_pydatetime() if len(forecast) else None)
    peak_3h_kw = float(ahead.p50.max()) if len(ahead) else None
    peak_3h_at = (pd.Timestamp(ahead.loc[ahead.p50.idxmax(), "target_ts"]).to_pydatetime()
                  if len(ahead) else None)
    midnight = datetime.combine(now.date(), datetime.min.time())
    today = data.plant_series(midnight, now)
    energy = float(today.kw.sum() / 60) if len(today) else 0.0
    cost = energy_cost(today.set_index("ts").kw, tariff) if len(today) else 0.0
    detections = data.detections(now, now - timedelta(hours=24))

    excess = projected - contract
    if excess > 0:
        level = Level.ALARM
        penalty = money(exceedance_penalty(projected, contract, tariff, now), tariff)
        headline = (f"Projected demand {projected:,.0f} kW is {excess:,.0f} kW above the "
                    f"{contract:,.0f} kW contract · penalty up to {penalty} this month")
        action = shed_advice(ctx, snapshot, excess)
    elif p_exceed >= ALARM_PROBABILITY:
        level = Level.ALARM
        headline = (f"{p_exceed:.0%} chance of exceeding the contract in "
                    f"{_interval(p_exceed_at)}, the riskiest interval of the next hour")
        action = shed_advice(ctx, snapshot, float(max(forecast.p90.max() - contract, 0.0)))
    elif p_exceed >= WARNING_PROBABILITY or projected >= ctx.warning_kw:
        level = Level.WARNING
        headline = (f"Projected demand {projected:,.0f} kW ({projected / contract:.0%} of "
                    f"contract) · {p_exceed:.0%} chance of exceeding it in "
                    f"{_interval(p_exceed_at)}")
        action = "Hold non-essential start-ups; be ready to pause EV charging"
    else:
        level = Level.OK
        headline = f"Demand {projected:,.0f} kW · {contract - projected:,.0f} kW below contract"
        action = "No action needed"
    return TickState(
        now, contract, snapshot, plant_kw, start, elapsed, so_far, projected, forecast,
        p_exceed, p_exceed_at, peak_3h_kw, peak_3h_at, detections, energy, cost,
        data.temperature(now), level, headline, action,
    )


def _interval(start: datetime | None) -> str:
    return "the next hour" if start is None else f"{start:%H:%M}-{start + INTERVAL:%H:%M}"


def shed_advice(ctx: Context, snapshot: pd.DataFrame, needed_kw: float) -> str:
    """Name the playbook actions, in playbook order, that cover the needed reduction."""
    from factory_energy.dashboard.playbook import shed_options

    chosen, total = [], 0.0
    for option in shed_options(ctx, snapshot):
        if option.shed_kw <= 0:
            continue
        chosen.append(option.action)
        total += option.shed_kw
        if total >= needed_kw:
            break
    if not chosen:
        return "No sheddable load available right now"
    shown = "; ".join(chosen[:2]) + (f"; +{len(chosen) - 2} more" if len(chosen) > 2 else "")
    return f"Shed {needed_kw:,.0f} kW: {shown} (covers {total:,.0f} kW)"
