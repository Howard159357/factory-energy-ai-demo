"""Plant data tools: overview, 15-minute demand, energy and cost, meter series and statistics.

Every query is parameterised and bounded to a 31-day window; there is no free-form SQL tool.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Literal

import pandas as pd
from pydantic import Field

from factory_energy.energy.demand import running_interval
from factory_energy.energy.tariff import PERIOD_NAMES, energy_cost, money, period
from factory_energy.tools.context import Arguments, PlantTime, ToolContext, Window, iso, num
from factory_energy.tools.registry import Tool

PLANT = "PLANT"
MAX_POINTS = 200
BUCKETS = (1, 5, 15, 60, 240, 1440)  # minutes
PLANT_MINUTES = """
    SELECT r.ts, SUM(r.kw) AS kw FROM meter_reading_minute r JOIN meter_master m USING (meter_id)
    WHERE m.include_in_plant_total AND r.ts >= ? AND r.ts < ? GROUP BY r.ts ORDER BY r.ts
"""
METRICS = {
    "kw": "kw",
    "pf": "pf",
    "voltage": "(r_v + s_v + t_v) / 3",
    "current": "(r_a + s_a + t_a) / 3",
}


class Empty(Arguments):
    pass


class DemandArgs(Window):
    pass


class EnergyArgs(Window):
    by: Literal["plant", "feeder", "meter"] = Field(
        default="feeder", description="Group energy by plant total, distribution board or meter")


class SeriesArgs(Window):
    meter_id: str = Field(description="A meter id such as MDB-3 or RF-02, or PLANT")
    metric: Literal["kw", "pf", "voltage", "current"] = "kw"


class StatsArgs(Window):
    meter_id: str = Field(description="A meter id such as AC-01, or PLANT for the plant total")


class StatusArgs(Arguments):
    as_of: PlantTime | None = Field(
        default=None, description="The moment to read, e.g. 2025-06-16T08:10; leave it out for "
                                  "the current time (or the end of the data)")


RUNNING_RATIO = 0.20  # above this share of its rating a load counts as running
IDLE_RATIO = 0.03  # above this (and not running) it is idling; below it, off
STATUS_MINUTES = 15  # the status is the mean of the minutes before the moment


def status_of(kw: float, rated_kw: float) -> str:
    """RUNNING, IDLE or OFF, the same classes as the dashboard and the glossary (EM-04)."""
    if kw > RUNNING_RATIO * rated_kw:
        return "RUNNING"
    return "IDLE" if kw > IDLE_RATIO * rated_kw else "OFF"


def _known(ctx: ToolContext, meter_id: str, allow_plant: bool = True) -> str:
    meter_id = meter_id.strip().upper()
    ids = {m.meter_id for m in (*ctx.catalog.feeders, *ctx.catalog.equipment)}
    if meter_id in ids or (allow_plant and meter_id == PLANT):
        return meter_id
    raise ValueError(f"unknown meter {meter_id!r}; call get_plant_overview for the meter list")


def _plant_minutes(ctx: ToolContext, args: Window) -> pd.DataFrame:
    frame = ctx.query(PLANT_MINUTES, (args.start, args.end))
    if frame.empty:
        raise LookupError("no readings in this window (the data covers 2025-01-01 to 2025-12-31)")
    return frame


def get_plant_overview(ctx: ToolContext, args: Empty) -> dict[str, Any]:
    span = ctx.query("SELECT MIN(ts) AS lo, MAX(ts) AS hi FROM meter_reading_minute").iloc[0]
    scenarios = ctx.query("SELECT scenario_id, title, replay_start, replay_end FROM scenarios "
                          "ORDER BY scenario_id")
    models = ctx.query("SELECT DISTINCT model FROM forecasts ORDER BY model").model.tolist() \
        if _has_table(ctx, "forecasts") else []
    return {
        "plant": ctx.settings.plant.name,
        "note": "fictional plant, all data synthetic",
        "timezone": ctx.settings.plant.timezone,
        "contract_capacity_kw": ctx.contract_kw,
        "warning_kw": ctx.contract_kw * ctx.settings.demand.warning_ratio,
        "demand_interval_min": ctx.settings.demand.interval_minutes,
        "data_from": iso(span.lo),
        "data_to": iso(min(span.hi, ctx.as_of) if ctx.as_of else span.hi),
        "current_time": iso(ctx.as_of),
        "tariff": ctx.settings.tariff.name,
        "feeders": [{"id": f.meter_id, "name": f.name, "rated_kw": f.rated_kw}
                    for f in ctx.catalog.feeders],
        "equipment": [{"id": e.meter_id, "name": e.name, "feeder": e.feeder,
                       "category": e.category, "rated_kw": e.rated_kw}
                      for e in ctx.catalog.equipment],
        "incident_scenarios": [
            {"id": r.scenario_id, "title": r.title, "from": iso(r.replay_start),
             "to": iso(r.replay_end)} for r in scenarios.itertuples()
            # Incidents still to come would give away the future: list finished ones only.
            if ctx.as_of is None or r.replay_end <= ctx.as_of
        ],
        "forecast_models": models,
    }


def _has_table(ctx: ToolContext, name: str) -> bool:
    found = ctx.query("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_name = ?",
                      (name,))
    return bool(found.n.iloc[0])


def get_demand(ctx: ToolContext, args: DemandArgs) -> dict[str, Any]:
    minutes = _plant_minutes(ctx, args).set_index("ts").kw
    interval = ctx.settings.demand.interval_minutes
    grouped = minutes.resample(f"{interval}min")
    counts = grouped.count()
    demand = grouped.mean()[counts == interval]
    running = None
    if len(counts) and 0 < counts.iloc[-1] < interval:
        # The window ends inside an interval (the present, during a replay). Project it the way
        # the dashboard alarm does, so an answer quotes the same figure as the alarm on screen.
        start = counts.index[-1]
        elapsed, so_far, projected = running_interval(
            [float(kw) for kw in minutes[minutes.index >= start]], interval)
        running = {
            "start": iso(start), "minutes_elapsed": elapsed, "average_so_far_kw": num(so_far),
            "projected_kw": num(projected),
            "projected_minus_contract_kw": num(projected - ctx.contract_kw),
            "method": "minutes so far plus the latest minute held to the end of the interval; "
                      "the figure the dashboard alarm shows",
        }
    if demand.empty:
        if running is None:
            raise LookupError("no complete 15-minute interval in this window")
        return {"contract_kw": ctx.contract_kw, "intervals": 0, "interval_in_progress": running}
    peak_at = demand.idxmax()
    over = demand[demand > ctx.contract_kw]
    result: dict[str, Any] = {
        "contract_kw": ctx.contract_kw,
        "intervals": int(demand.size),
        "peak_kw": num(demand.max()), "peak_interval_start": iso(peak_at),
        "peak_contract_ratio": num(demand.max() / ctx.contract_kw, 3),
        "mean_kw": num(demand.mean()),
        "intervals_over_contract": int(over.size),
        "over_contract": [{"start": iso(ts), "kw": num(kw)} for ts, kw in over.head(24).items()],
    }
    if running is not None:
        result["interval_in_progress"] = running
    if demand.size <= 96:
        result["series"] = [{"start": iso(ts), "kw": num(kw)} for ts, kw in demand.items()]
    else:
        daily = demand.groupby(demand.index.date)
        result["daily"] = [
            {"day": str(day), "peak_kw": num(day_demand.max()),
             "peak_at": iso(day_demand.idxmax()), "mean_kw": num(day_demand.mean())}
            for day, day_demand in daily
        ]
    return result


def get_energy(ctx: ToolContext, args: EnergyArgs) -> dict[str, Any]:
    tariff = ctx.settings.tariff
    if args.by == "plant":
        series = {PLANT: _plant_minutes(ctx, args).set_index("ts").kw}
        names = {PLANT: "Plant total"}
    else:
        meters = ctx.catalog.feeders if args.by == "feeder" else ctx.catalog.equipment
        names = {m.meter_id: m.name for m in meters}
        placeholders = ", ".join("?" for _ in names)
        frame = ctx.query(
            f"SELECT ts, meter_id, kw FROM meter_reading_minute WHERE ts >= ? AND ts < ? "
            f"AND meter_id IN ({placeholders})", (args.start, args.end, *names))
        if frame.empty:
            raise LookupError("no readings in this window")
        pivot = frame.pivot(index="ts", columns="meter_id", values="kw").sort_index()
        series = {meter: pivot[meter].fillna(0.0) for meter in pivot.columns}
    totals = sorted(((meter, float(kw.sum() / 60.0), energy_cost(kw, tariff))
                     for meter, kw in series.items()), key=lambda row: row[1], reverse=True)
    total = sum(kwh for _, kwh, _ in totals)
    items = [{"id": meter, "name": names.get(meter, meter), "kwh": num(kwh),
              "energy_cost_ntd": num(cost, 0), "share": num(kwh / total, 3) if total else None}
             for meter, kwh, cost in totals]
    result: dict[str, Any] = {
        "by": args.by, "total_kwh": num(total),
        "total_energy_cost": money(sum(cost for _, _, cost in totals), tariff),
        "note": "energy charge only; the demand charge and power-factor adjustment are separate",
        "items": items,
    }
    if args.by == "plant":
        kw = series[PLANT]
        periods = period(pd.DatetimeIndex(kw.index), tariff)
        result["kwh_by_tou_period"] = {
            PERIOD_NAMES.get(name, name): num(float(kw[periods.values == name].sum() / 60.0))
            for name in sorted(set(periods))
        }
    return result


def _bucket(args: Window) -> int:
    span = (args.end - args.start).total_seconds() / 60
    return next((b for b in BUCKETS if span / b <= MAX_POINTS), BUCKETS[-1])


def get_meter_series(ctx: ToolContext, args: SeriesArgs) -> dict[str, Any]:
    meter = _known(ctx, args.meter_id)
    bucket = _bucket(args)
    if meter == PLANT:
        if args.metric != "kw":
            raise ValueError("only kw is available for PLANT")
        minutes = _plant_minutes(ctx, args).set_index("ts").kw
    else:
        frame = ctx.query(
            f"SELECT ts, {METRICS[args.metric]} AS value FROM meter_reading_minute "
            "WHERE meter_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (meter, args.start, args.end))
        if frame.empty:
            raise LookupError("no readings in this window")
        minutes = frame.set_index("ts").value
    resampled = minutes.resample(f"{bucket}min")
    mean, peak = resampled.mean(), resampled.max()
    digits = 3 if args.metric == "pf" else 1
    # A summary of the whole window first, then compact columns: models answer most questions
    # from the summary and the series stays far below the agent's tool-result size cap.
    return {
        "meter_id": meter, "metric": args.metric,
        "window_summary": {
            "mean": num(minutes.mean(), digits), "min": num(minutes.min(), digits),
            "max": num(minutes.max(), digits), "max_at": iso(minutes.idxmax()),
            "minutes": int(minutes.count()),
        },
        "series": {
            "first_bucket_start": iso(mean.index[0]), "bucket_minutes": bucket,
            "mean": [num(v, digits) for v in mean.to_numpy()],
            "max": [num(v, digits) for v in peak.to_numpy()],
        },
    }


def compute_stats(ctx: ToolContext, args: StatsArgs) -> dict[str, Any]:
    meter = _known(ctx, args.meter_id)
    if meter == PLANT:
        frame = _plant_minutes(ctx, args).assign(pf=math.nan)
        rated = sum(f.rated_kw for f in ctx.catalog.feeders)
    else:
        frame = ctx.query("SELECT ts, kw, pf FROM meter_reading_minute "
                          "WHERE meter_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
                          (meter, args.start, args.end))
        if frame.empty:
            raise LookupError("no readings in this window")
        spec = next(m for m in (*ctx.catalog.feeders, *ctx.catalog.equipment)
                    if m.meter_id == meter)
        rated = spec.rated_kw
    kw = frame.set_index("ts").kw
    night = kw[(kw.index.hour >= 2) & (kw.index.hour < 5)]
    return {
        "meter_id": meter, "rated_kw": rated, "minutes": int(kw.size),
        "energy_kwh": num(kw.sum() / 60.0),
        "mean_kw": num(kw.mean()), "p95_kw": num(kw.quantile(0.95)),
        "max_kw": num(kw.max()), "max_at": iso(kw.idxmax()), "min_kw": num(kw.min()),
        "night_base_kw_median_02_05": num(night.median()) if not night.empty else None,
        "share_of_time_running_above_20pct_rating": num((kw > 0.2 * rated).mean(), 3),
        "mean_power_factor": num(frame.pf.mean(), 3),
    }


def get_equipment_status(ctx: ToolContext, args: StatusArgs) -> dict[str, Any]:
    moment = args.as_of or ctx.as_of
    if moment is None:
        moment = ctx.query("SELECT MAX(ts) AS hi FROM meter_reading_minute").hi.iloc[0] \
            + timedelta(minutes=1)
    start = moment - timedelta(minutes=STATUS_MINUTES)
    loads = ctx.catalog.equipment
    placeholders = ", ".join("?" for _ in loads)
    frame = ctx.query(
        f"SELECT meter_id, AVG(kw) AS kw FROM meter_reading_minute WHERE ts >= ? AND ts < ? "
        f"AND meter_id IN ({placeholders}) GROUP BY meter_id",
        (start, moment, *(e.meter_id for e in loads)))
    if frame.empty:
        raise LookupError("no readings before this moment (the data covers 2025-01-01 to "
                          "2025-12-31)")
    kw = dict(zip(frame.meter_id, frame.kw, strict=True))
    # The latest complete minute: the present load, which load-shed amounts are taken from
    # (SOP-03) and which the dashboard's playbook shows. A load that just changed (a second
    # EV charger starting) differs from its 15-minute mean.
    latest = ctx.query(
        f"SELECT meter_id, kw FROM meter_reading_minute WHERE ts = ? "
        f"AND meter_id IN ({placeholders})",
        (moment - timedelta(minutes=1), *(e.meter_id for e in loads)))
    now_kw = dict(zip(latest.meter_id, latest.kw, strict=True))
    items = []
    for load in loads:
        value = float(kw.get(load.meter_id, 0.0))
        items.append({"id": load.meter_id, "name": load.name, "feeder": load.feeder,
                      "rated_kw": load.rated_kw, "kw": num(value),
                      "kw_now": num(float(now_kw.get(load.meter_id, 0.0))),
                      "share_of_rating": num(value / load.rated_kw, 3) if load.rated_kw else None,
                      "state": status_of(value, load.rated_kw)})
    counts = {state: sum(1 for i in items if i["state"] == state)
              for state in ("RUNNING", "IDLE", "OFF")}
    return {
        "as_of": iso(moment), "averaged_minutes": STATUS_MINUTES,
        "fields": "kw is the mean over the averaged minutes and sets the state; kw_now is the "
                  "latest minute, the present load to use for load-shed amounts",
        "rule": f"RUNNING above {RUNNING_RATIO:.0%} of rating, IDLE above {IDLE_RATIO:.0%}, "
                "otherwise OFF",
        "counts": counts, "equipment": items,
    }


TOOLS = [
    Tool("get_plant_overview",
         "Plant facts: contract capacity, data range, distribution boards and sub-metered "
         "equipment with ratings, labelled incident scenarios with dates, forecast models.",
         Empty, "read", get_plant_overview),
    Tool("get_demand",
         "15-minute plant demand in a window (max 31 days): peak kW and when, intervals above "
         "the contract, the series (<= 1 day) or daily peaks (longer windows). When the window "
         "ends inside an interval, also that interval's projected demand, as the alarm shows.",
         DemandArgs, "read", get_demand),
    Tool("get_energy",
         "Energy (kWh) and energy cost in NT$ in a window (max 31 days), by plant, distribution "
         "board (feeder) or sub-metered equipment; plant view adds kWh per time-of-use period.",
         EnergyArgs, "read", get_energy),
    Tool("get_meter_series",
         "Time series of one meter (or PLANT) in a window: kW, power factor, voltage or current, "
         "averaged into at most 200 buckets.",
         SeriesArgs, "read", get_meter_series),
    Tool("compute_stats",
         "Statistics of one meter (or PLANT) in a window: energy, mean, p95, max and when, "
         "night base load, share of time running, mean power factor.",
         StatsArgs, "read", compute_stats),
    Tool("get_equipment_status",
         "Status of every sub-metered load at one moment (default: now): mean kW over the "
         "preceding 15 minutes, share of rating and RUNNING / IDLE / OFF, and kw_now, the "
         "present load (latest minute). Use it for questions about what is running, idle or "
         "off instead of one series per meter; compute load-shed amounts from kw_now.",
         StatusArgs, "read", get_equipment_status),
]
