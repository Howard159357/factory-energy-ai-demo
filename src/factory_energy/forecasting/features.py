"""Turn the 15-minute plant demand history into supervised learning rows.

A row is "standing at the end of interval i, predict interval i + h". Only information that
would really be available at that moment is used: demand up to interval i, the production
calendar (planned in advance) and a weather *forecast* for the target time.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from factory_energy.simulator.timeline import rng_for

INTERVALS_PER_DAY = 96
FEATURE_VERSION = "1"  # bump when make_rows changes, to invalidate cached backtests
DAY_TYPES = ("WORKDAY", "SATURDAY", "SUNDAY", "HOLIDAY")


@dataclass(frozen=True)
class DemandHistory:
    """One row per demand interval: plant kW, outdoor temperature and the day's plan."""

    frame: pd.DataFrame  # index: interval start; columns: kw, temp_c, day_type, overtime

    @property
    def kw(self) -> pd.Series:
        return self.frame.kw


def load_history(
    connection: duckdb.DuckDBPyConnection, interval_minutes: int = 15
) -> DemandHistory:
    bucket = f"INTERVAL {interval_minutes} MINUTE"
    frame = connection.execute(f"""
        WITH demand AS (
            SELECT time_bucket({bucket}, r.ts) AS w,
                   ROUND(SUM(r.kw) / {interval_minutes}, 3) AS kw
            FROM meter_reading_minute r JOIN meter_master m USING (meter_id)
            WHERE m.include_in_plant_total GROUP BY 1),
        weather AS (
            SELECT time_bucket({bucket}, ts) AS w, ROUND(AVG(temp_c), 3) AS temp_c
            FROM weather_minute GROUP BY 1)
        SELECT d.w, d.kw, w.temp_c, c.day_type, c.overtime
        FROM demand d JOIN weather w USING (w)
        JOIN production_calendar c ON c.day = CAST(d.w AS DATE)
        ORDER BY d.w""").df()
    return DemandHistory(frame.set_index("w"))


def temperature_forecast(
    actual: pd.Series, horizon: int, seed: int = 42
) -> np.ndarray:
    """Actual temperature plus a forecast error that grows with lead time."""
    sd = 0.3 + 1.5 * min(horizon / INTERVALS_PER_DAY, 1.0)
    noise = rng_for(seed, "temperature_forecast", str(horizon)).normal(0.0, sd, len(actual))
    return np.asarray(actual.to_numpy() + noise)


def make_rows(history: DemandHistory, horizon: int) -> pd.DataFrame:
    """Feature rows indexed by *target* interval, with the issue time and the true value."""
    f = history.frame
    kw = f.kw
    target = f.index
    rows = pd.DataFrame(index=target)
    rows["issue"] = pd.Series(target, index=target).shift(horizon)
    rows["y"] = kw
    # What the plant looked like at issue time (the latest completed intervals).
    last = kw.shift(horizon)
    rows["last"] = last
    rows["last_mean_1h"] = last.rolling(4).mean()
    rows["last_trend_1h"] = last - kw.shift(horizon + 4)
    rows["same_time_yesterday"] = kw.shift(INTERVALS_PER_DAY) if horizon <= INTERVALS_PER_DAY \
        else np.nan
    rows["same_time_last_week"] = kw.shift(7 * INTERVALS_PER_DAY)
    # What is known in advance about the target interval.
    slot = target.hour * 4 + target.minute // 15
    rows["slot_sin"] = np.sin(2 * np.pi * slot / INTERVALS_PER_DAY)
    rows["slot_cos"] = np.cos(2 * np.pi * slot / INTERVALS_PER_DAY)
    rows["slot"] = slot
    rows["weekday"] = target.weekday
    for kind in DAY_TYPES:
        rows[f"is_{kind.lower()}"] = (f.day_type == kind).astype(float)
    rows["overtime"] = f.overtime.astype(float)
    previous_day = f.day_type.shift(INTERVALS_PER_DAY)
    rows["after_rest_day"] = (previous_day != "WORKDAY").astype(float)
    rows["temp_forecast"] = temperature_forecast(f.temp_c, horizon)
    rows["temp_now"] = f.temp_c.shift(horizon)
    return rows.dropna(subset=["issue", "last", "same_time_last_week", "last_mean_1h"])


FEATURES = [
    "last", "last_mean_1h", "last_trend_1h", "same_time_yesterday", "same_time_last_week",
    "slot_sin", "slot_cos", "slot", "weekday", "is_workday", "is_saturday", "is_sunday",
    "is_holiday", "overtime", "after_rest_day", "temp_forecast", "temp_now",
]
