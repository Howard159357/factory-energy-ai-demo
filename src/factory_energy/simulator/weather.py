from __future__ import annotations

import numpy as np

from factory_energy.simulator.timeline import EPOCH, FloatArray, Timeline, rng_for

ANNUAL_MEAN_C = 23.5
SEASONAL_AMPLITUDE_C = 6.0
PEAK_DAY_OF_YEAR = 201  # late July
DIURNAL_AMPLITUDE_C = 4.0
PEAK_HOUR = 14.5
DAILY_ANOMALY_SD_C = 1.6
DAILY_ANOMALY_PERSISTENCE = 0.7


def outdoor_temperature(timeline: Timeline, seed: int) -> FloatArray:
    """Subtropical outdoor temperature: season + day/night cycle + persistent weather."""
    day_of_year = np.array([d.timetuple().tm_yday for d in timeline.dates], dtype=np.float64)
    seasonal = ANNUAL_MEAN_C + SEASONAL_AMPLITUDE_C * np.cos(
        2 * np.pi * (day_of_year - PEAK_DAY_OF_YEAR) / 365.25
    )
    # Persistent weather is integrated from a fixed epoch so every window sees the same days.
    skip = (timeline.start - EPOCH).days
    if skip < 0:
        raise ValueError(f"simulation must start on or after {EPOCH}")
    shocks = rng_for(seed, "weather").normal(0.0, DAILY_ANOMALY_SD_C, skip + timeline.days)
    anomaly_all = np.empty(shocks.size)
    level = 0.0
    for index, shock in enumerate(shocks):
        level = DAILY_ANOMALY_PERSISTENCE * level + shock
        anomaly_all[index] = level
    anomaly = anomaly_all[skip:]
    # Interpolate daily values at noon so the series has no midnight steps.
    noon = np.arange(timeline.days) * 1440 + 720
    minutes = np.arange(timeline.minutes)
    daily = np.interp(minutes, noon, seasonal + anomaly)
    diurnal = DIURNAL_AMPLITUDE_C * np.cos(2 * np.pi * (timeline.hour - PEAK_HOUR) / 24)
    jitter = np.concatenate([
        rng_for(seed, "weather", day.isoformat()).normal(0.0, 0.15, 1440)
        for day in timeline.dates
    ])
    return np.asarray(np.round(daily + diurnal + jitter, 2))
