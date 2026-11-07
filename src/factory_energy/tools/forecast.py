"""Forecast and what-if tools."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import Field

from factory_energy.energy.tariff import exceedance_penalty, money
from factory_energy.simulator.scenarios import SimultaneousStart, load_scenarios
from factory_energy.simulator.whatif import staggered_start
from factory_energy.tools.context import Arguments, PlantTime, ToolContext, iso, num
from factory_energy.tools.registry import Tool

INTERVAL = timedelta(minutes=15)
WARNING, ALARM = 0.2, 0.5


class ForecastArgs(Arguments):
    as_of: PlantTime = Field(description="The moment the forecast is read, e.g. 2025-07-23T13:20")
    horizon_minutes: Literal[15, 30, 60, 120, 180, 1440] = Field(
        default=60, description="Furthest horizon to return")
    model: Literal["lightgbm", "hgb", "linear", "profile", "ensemble"] = "lightgbm"


class WhatIfArgs(Arguments):
    scenario_id: str = Field(default="S2", pattern=r"^S\d{1,2}$",
                             description="A simultaneous-start scenario, normally S2")
    stagger_minutes: int = Field(default=15, ge=5, le=60)


def get_forecast(ctx: ToolContext, args: ForecastArgs) -> dict[str, Any]:
    # Only a forecast whose issuing interval has closed is known at `as_of`.
    issued = ctx.query("SELECT MAX(issue_ts) AS t FROM forecasts WHERE model = ? AND issue_ts <= ?",
                       (args.model, args.as_of - INTERVAL)).t.iloc[0]
    if issued is None or str(issued) == "NaT":
        raise LookupError("no forecast issued before this time (forecasts cover Jun-Dec 2025)")
    rows = ctx.query(
        "SELECT target_ts, horizon_min, p10, p50, p90, p_exceed, actual FROM forecasts "
        "WHERE model = ? AND issue_ts = ? AND horizon_min <= ? ORDER BY horizon_min",
        (args.model, issued, args.horizon_minutes))
    accuracy = ctx.query(
        "SELECT horizon_min, AVG(ABS(p50 - actual)) AS mae, SUM(ABS(p50 - actual)) / SUM(actual) "
        "AS wape FROM forecasts WHERE model = ? AND actual IS NOT NULL GROUP BY horizon_min",
        (args.model,)).set_index("horizon_min")
    next_hour = rows[rows.horizon_min <= 60].p_exceed
    worst = float(next_hour.max()) if not next_hour.empty else 0.0
    riskiest = (rows.loc[next_hour.idxmax(), "target_ts"] if not next_hour.empty else None)
    level = "ALARM" if worst >= ALARM else "WARNING" if worst >= WARNING else "OK"
    return {
        "model": args.model, "issued_at": iso(issued), "contract_kw": ctx.contract_kw,
        "next_hour_max_probability_of_exceeding_contract": num(worst, 3),
        # The dashboard shows this maximum; name its interval so it is not read as "in 1 hour".
        "next_hour_max_interval_start": iso(riskiest) if riskiest is not None else None,
        "next_hour_alert_level": level,
        "forecasts": [
            # Both ends: given only the start, a model wrote "the hour ending 09:00" for the
            # 09:00-09:15 interval.
            {"interval_start": iso(r.target_ts), "interval_end": iso(r.target_ts + INTERVAL),
             "horizon_min": int(r.horizon_min),
             "p10_kw": num(r.p10), "p50_kw": num(r.p50), "p90_kw": num(r.p90),
             "p_exceed": num(r.p_exceed, 3),
             # The measured value is only shown once its interval has closed.
             "actual_kw": num(r.actual) if r.target_ts + INTERVAL <= args.as_of else None,
             "backtest_mae_kw": num(accuracy.mae.get(r.horizon_min)),
             "backtest_wape": num(accuracy.wape.get(r.horizon_min), 4)}
            for r in rows.itertuples()
        ],
    }


def whatif_staggered_start(ctx: ToolContext, args: WhatIfArgs) -> dict[str, Any]:
    scenario = next((s for s in load_scenarios() if s.id == args.scenario_id), None)
    if scenario is None:
        raise LookupError(f"unknown scenario {args.scenario_id}")
    # Re-simulating the whole day reveals its peak, so it is allowed only after the day ends.
    days = [e.at.date() for e in scenario.events if isinstance(e, SimultaneousStart)]
    day_end = (datetime.combine(days[0], datetime.min.time()) + timedelta(days=1)
               if days else None)
    if ctx.as_of is not None and day_end is not None and ctx.as_of < day_end:
        raise LookupError("the what-if re-simulates the whole day, so it is available only "
                          "after that day has ended")
    seed = int(ctx.query("SELECT seed FROM simulation_runs LIMIT 1").seed.iloc[0])
    result = staggered_start(scenario, ctx.settings, ctx.catalog, seed, args.stagger_minutes)
    if result is None:
        raise ValueError(f"{args.scenario_id} is not a simultaneous-start scenario")
    interval = ctx.settings.demand.interval_minutes
    peak_index = int(result.actual_kw.reshape(-1, interval).mean(axis=1).argmax())
    peak_at = datetime.combine(result.day, datetime.min.time()) + peak_index * INTERVAL
    tariff = ctx.settings.tariff
    avoided = (exceedance_penalty(result.actual_peak_kw, ctx.contract_kw, tariff, peak_at)
               - exceedance_penalty(result.staggered_peak_kw, ctx.contract_kw, tariff, peak_at))
    return {
        "scenario": scenario.id, "day": str(result.day), "stagger_minutes": result.stagger_minutes,
        "contract_kw": ctx.contract_kw,
        "actual_peak_kw": num(result.actual_peak_kw), "actual_peak_interval": iso(peak_at),
        "staggered_peak_kw": num(result.staggered_peak_kw),
        "reduction_kw": num(result.reduction_kw),
        "exceedance_penalty_avoided": money(avoided, tariff),
        "note": "re-simulation of the same morning with machines started one after another",
    }


TOOLS = [
    Tool("get_forecast",
         "Demand forecast known at a given moment: P10/P50/P90 kW per horizon, probability of "
         "exceeding the contract, next-hour alert level, and the model's backtest error.",
         ForecastArgs, "read", get_forecast),
    Tool("whatif_staggered_start",
         "Re-simulate a simultaneous-start morning with machines started N minutes apart and "
         "report the peak demand before and after and the exceedance penalty avoided.",
         WhatIfArgs, "read", whatif_staggered_start),
]
