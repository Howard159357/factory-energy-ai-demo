from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PlantData:
    """Minute readings pivoted to one column per meter, plus the context detectors need."""

    kw: pd.DataFrame  # index: ts (1-minute), columns: meter_id
    pf: pd.DataFrame
    meters: pd.DataFrame  # meter_master indexed by meter_id
    day_type: pd.Series  # index: ts, value: WORKDAY / SATURDAY / SUNDAY / HOLIDAY
    temperature: pd.Series
    contract_kw: float
    interval_minutes: int

    @property
    def feeder_ids(self) -> list[str]:
        mask = self.meters.meter_type == "FEEDER"
        return list(self.meters.index[mask])

    @property
    def equipment_ids(self) -> list[str]:
        return list(self.meters.index[self.meters.meter_type == "EQUIPMENT"])

    def rated(self, meter_id: str) -> float:
        return float(self.meters.at[meter_id, "rated_kw"])

    def category(self, meter_id: str) -> str:
        return str(self.meters.at[meter_id, "category"])

    @property
    def plant_kw(self) -> pd.Series:
        return self.kw[self.feeder_ids].sum(axis=1)


def _pivot(
    connection: duckdb.DuckDBPyConnection, metric: str, start: datetime, end: datetime
) -> pd.DataFrame:
    if metric not in {"kw", "pf"}:
        raise ValueError("unsupported metric")
    frame = connection.execute(
        f"SELECT ts, meter_id, {metric} AS v FROM meter_reading_minute "
        "WHERE ts >= ? AND ts < ?",
        (start, end),
    ).df()
    return frame.pivot(index="ts", columns="meter_id", values="v").sort_index()


def load_plant_data(
    connection: duckdb.DuckDBPyConnection,
    contract_kw: float,
    interval_minutes: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> PlantData:
    bounds = connection.execute("SELECT MIN(ts), MAX(ts) FROM meter_reading_minute").fetchone()
    if bounds is None or bounds[0] is None:
        raise ValueError("database has no readings")
    lo = start or bounds[0]
    hi = end or bounds[1] + pd.Timedelta(minutes=1)
    kw = _pivot(connection, "kw", lo, hi)
    pf = _pivot(connection, "pf", lo, hi)
    meters = connection.execute("SELECT * FROM meter_master").df().set_index("meter_id")
    calendar = connection.execute("SELECT day, day_type FROM production_calendar").df()
    by_day = dict(zip(pd.to_datetime(calendar.day).dt.date, calendar.day_type, strict=True))
    day_type = pd.Series([by_day.get(d) for d in kw.index.date], index=kw.index)
    weather = connection.execute(
        "SELECT ts, temp_c FROM weather_minute WHERE ts >= ? AND ts < ? ORDER BY ts", (lo, hi)
    ).df()
    temperature = weather.set_index("ts").temp_c.reindex(kw.index)
    return PlantData(
        kw=kw.astype(np.float64),
        pf=pf.astype(np.float64),
        meters=meters,
        day_type=day_type,
        temperature=temperature,
        contract_kw=contract_kw,
        interval_minutes=interval_minutes,
    )


def runs(mask: pd.Series, min_length: int, max_gap: int = 0) -> list[tuple[int, int]]:
    """[start, end) index ranges where mask is true for >= min_length, bridging short gaps."""
    values = mask.to_numpy(dtype=bool)
    edges = np.diff(np.concatenate(([0], values.astype(np.int8), [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    merged: list[list[int]] = []
    for s, e in zip(starts, ends, strict=True):
        if merged and s - merged[-1][1] <= max_gap:
            merged[-1][1] = int(e)
        else:
            merged.append([int(s), int(e)])
    return [(s, e) for s, e in merged if e - s >= min_length]
