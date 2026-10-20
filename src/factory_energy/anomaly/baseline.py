"""Layer 2: statistical baselines that catch slow drifts rules cannot see."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd

from factory_energy.anomaly.data import PlantData
from factory_energy.anomaly.models import Detection, Layer

NIGHT = (time(2, 0), time(5, 0))
HISTORY_DAYS = 6  # same-day-type nights used as the expected value
CUSUM_K = 0.5  # allowance, in robust standard deviations
CUSUM_H = 8.0  # alarm threshold, in robust standard deviations
MIN_SIGMA_KW = 1.0
MIN_SIGMA_SHARE = 0.02
MIN_EXCESS_KW = 3.0


def nightly_base(data: PlantData, meters: list[str]) -> pd.DataFrame:
    """Mean kW between 02:00 and 05:00 for a group of meters, one row per day."""
    group = data.kw[meters].sum(axis=1)
    night = group.between_time(*NIGHT, inclusive="left")
    frame = night.groupby(night.index.date).mean().to_frame("kw")
    day_type = data.day_type.groupby(data.day_type.index.date).first()
    # 02:00-05:00 belongs to the previous day's night shift: compare nights that follow a
    # workday (around-the-clock lines still running) with each other, and the rest together.
    frame["kind"] = np.where(day_type.shift(1) == "WORKDAY", "after_workday", "after_rest_day")
    return frame


def cusum_drift(
    frame: pd.DataFrame,
) -> list[tuple[datetime, datetime, float, datetime]]:
    """Upward drift episodes (onset, end, peak excess kW, alarm night) from nightly base load."""
    history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=HISTORY_DAYS))
    residuals: list[float] = []
    for _, row in frame.iterrows():
        past = history[row.kind]
        if len(past) >= 3:
            residuals.append(row.kw - float(np.median(past)))
        past.append(row.kw)
    spread = 1.4826 * float(np.median(np.abs(residuals))) if residuals else 1.0
    # Floor the noise estimate so tiny, operationally meaningless wiggles never alarm.
    sigma = max(spread, MIN_SIGMA_SHARE * float(frame.kw.median()), MIN_SIGMA_KW)

    history = defaultdict(lambda: deque(maxlen=HISTORY_DAYS))
    episodes: list[tuple[datetime, datetime, float, datetime]] = []
    score, onset, alarm, excess, calm = 0.0, None, False, 0.0, 0
    alarm_day: object = None
    for day, row in frame.iterrows():
        past = history[row.kind]
        if len(past) < 3:
            past.append(row.kw)
            continue
        residual = row.kw - float(np.median(past))
        previous = score
        score = max(0.0, score + residual / sigma - CUSUM_K)
        if previous == 0.0 and score > 0.0:
            onset = day
        if not alarm and score > CUSUM_H and residual > MIN_EXCESS_KW:
            alarm, excess, alarm_day = True, residual, day
        if alarm:
            excess = max(excess, residual)
            calm = calm + 1 if residual < sigma else 0
            if calm >= 2:  # back to normal: close the episode, resume learning
                episodes.append((_at(onset), _at(day), excess, _at(alarm_day)))
                alarm, score, calm = False, 0.0, 0
            continue  # freeze the baseline while the anomaly lasts
        if score == 0.0:
            onset = None
            past.append(row.kw)  # learn only from nights that look normal
    if alarm:
        episodes.append((_at(onset), _at(frame.index[-1]), excess, _at(alarm_day)))
    return episodes


def _at(day: object) -> datetime:
    return datetime.combine(pd.Timestamp(str(day)).date(), NIGHT[0])


# Systems whose night load should be flat all year. Feeders that carry weather-driven loads
# (HVAC, office air conditioning) would need temperature normalisation before this test applies.
SYSTEMS: dict[str, tuple[str, str]] = {
    # system name -> (event type, meter id prefix)
    "compressed_air": ("AIR_LEAK", "AC-"),
}


def baseline_drift(data: PlantData) -> list[Detection]:
    detections: list[Detection] = []
    groups: dict[str, tuple[str, list[str]]] = {
        name: (kind, [m for m in data.equipment_ids if m.startswith(prefix)])
        for name, (kind, prefix) in SYSTEMS.items()
    }
    for name, (event_type, meters) in groups.items():
        for onset, end, excess, alarm_at in cusum_drift(nightly_base(data, meters)):
            detections.append(Detection(
                Layer.BASELINE, "baseline:cusum_night", event_type, tuple(meters),
                onset, end, "medium", excess,
                f"{name} night base load up to {excess:,.1f} kW above its usual level "
                f"from {onset:%Y-%m-%d}",
                alarm_at + timedelta(hours=4),  # nightly batch has the 02:00-05:00 window
            ))
    return detections
