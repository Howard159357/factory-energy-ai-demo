from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from statistics import mean

from factory_energy.energy.completeness import minute_plant_totals
from factory_energy.energy.models import MetricResult, Reading

INTERVAL_MINUTES = 15


def interval_start(ts: datetime, minutes: int = INTERVAL_MINUTES) -> datetime:
    """Start of the fixed demand interval (e.g. :00, :15, :30, :45) that contains ts."""
    floored = ts.replace(second=0, microsecond=0)
    return floored - timedelta(minutes=floored.minute % minutes)


def _window_demand(
    rows: Iterable[Reading], feeder_ids: list[str], start: datetime, end: datetime
) -> tuple[float | None, int]:
    totals = minute_plant_totals((r for r in rows if start <= r["ts"] < end), feeder_ids)
    values = [t.kw for t in totals.values() if t.complete and t.kw is not None]
    return (mean(values) if values else None), len(values)


def fixed_demand(
    rows: Iterable[Reading],
    feeder_ids: list[str],
    start: datetime,
    minutes: int = INTERVAL_MINUTES,
) -> MetricResult:
    end = start + timedelta(minutes=minutes)
    value, count = _window_demand(rows, feeder_ids, start, end)
    complete = count == minutes
    return MetricResult(
        value, "kW", start, end, complete, count / minutes,
        [] if complete else ["DEMAND_WINDOW_INCOMPLETE"],
    )


def rolling_demand(
    rows: Iterable[Reading], feeder_ids: list[str], end: datetime, minutes: int = INTERVAL_MINUTES
) -> MetricResult:
    return fixed_demand(rows, feeder_ids, end - timedelta(minutes=minutes), minutes)


def partial_demand(
    rows: Iterable[Reading],
    feeder_ids: list[str],
    as_of: datetime,
    minutes: int = INTERVAL_MINUTES,
) -> MetricResult:
    """Average so far inside the interval that is still in progress at as_of."""
    start = interval_start(as_of, minutes)
    value, count = _window_demand(rows, feeder_ids, start, as_of)
    return MetricResult(
        value, "kW", start, as_of, False, count / minutes, ["DEMAND_WINDOW_IN_PROGRESS"]
    )


def running_interval(
    kw: Sequence[float], minutes: int = INTERVAL_MINUTES
) -> tuple[int, float, float]:
    """Demand-controller view of the interval still running, from its minutes so far:
    (minutes elapsed, average so far, projected). The projection holds the latest minute to the
    end of the interval. The dashboard alarm and the get_demand tool both use it."""
    if not kw:
        return 0, 0.0, 0.0
    elapsed = len(kw)
    projected = (sum(kw) + kw[-1] * max(minutes - elapsed, 0)) / minutes
    return elapsed, sum(kw) / elapsed, projected


def peak_demand(windows: Iterable[MetricResult]) -> MetricResult:
    complete = [w for w in windows if w.complete and w.value is not None]
    if not complete:
        return MetricResult(
            None, "kW", complete=False, coverage_ratio=0.0,
            warnings=["NO_COMPLETE_DEMAND_WINDOW"],
        )
    return max(complete, key=lambda w: w.value or 0.0)


def contract_usage(
    demand_kw: float | None, contract_capacity_kw: float | None
) -> tuple[float | None, float | None]:
    """Return (usage ratio, remaining kW) against the contract capacity."""
    if demand_kw is None or contract_capacity_kw is None:
        return None, None
    if contract_capacity_kw <= 0:
        raise ValueError("contract capacity must be positive")
    return demand_kw / contract_capacity_kw, contract_capacity_kw - demand_kw
