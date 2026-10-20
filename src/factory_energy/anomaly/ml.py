"""Layer 3: IsolationForest over daily equipment fingerprints, for patterns no rule anticipates."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from factory_energy.anomaly.data import PlantData
from factory_energy.anomaly.models import Detection, Layer

CONTAMINATION = 0.01  # share of meter-days the forest treats as outliers
MIN_SCORE = 0.015  # report only clearly isolated days
CONTEXT_FEATURES = ("temp",)
# A load that barely moves all year (server room, EV bank) has no "shape" to be unusual about;
# the forest would only pick up noise. Such meters are skipped.
STEADY_CV = 0.05  # std / mean of the minute readings


def is_steady(data: PlantData, meter_id: str) -> bool:
    kw = data.kw[meter_id]
    mean = float(kw.mean())
    return mean > 0 and float(kw.std()) / mean < STEADY_CV


def daily_features(data: PlantData, meter_id: str) -> pd.DataFrame:
    """One row per day: shape of the load curve relative to the machine's rating."""
    kw = data.kw[meter_id] / data.rated(meter_id)
    day = kw.index.date
    hour = kw.index.hour
    frame = pd.DataFrame({
        "mean": kw.groupby(day).mean(),
        "p95": kw.groupby(day).quantile(0.95),
        "std": kw.groupby(day).std(),
        "night": kw[(hour >= 0) & (hour < 6)].groupby(day[(hour >= 0) & (hour < 6)]).mean(),
        "evening": kw[hour >= 20].groupby(day[hour >= 20]).mean(),
        "on_share": (kw > 0.2).groupby(day).mean(),
        "pf": data.pf[meter_id].groupby(day).mean(),
    }).fillna(0.0)
    kinds = data.day_type.groupby(data.day_type.index.date).first()
    for kind in ("WORKDAY", "SATURDAY", "SUNDAY", "HOLIDAY"):
        frame[f"is_{kind.lower()}"] = (kinds == kind).astype(float)
    frame["temp"] = data.temperature.groupby(data.temperature.index.date).mean()
    return frame


def day_scores(features: pd.DataFrame, seed: int = 0) -> np.ndarray:
    """Outlier score per day (higher = more isolated; > 0 means outside the normal mass)."""
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(features.to_numpy())
    model = IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=seed)
    return np.asarray(-model.fit(scaled).decision_function(scaled))


def isolation_forest(data: PlantData, seed: int = 0) -> list[Detection]:
    detections: list[Detection] = []
    for meter in data.equipment_ids:
        if is_steady(data, meter):
            continue
        features = daily_features(data, meter)
        if len(features) < 30:
            continue
        scores = day_scores(features, seed)
        flagged = (scores >= MIN_SCORE) & ~_calendar_explained(data, features.index)
        for day, score in zip(features.index[flagged], scores[flagged], strict=True):
            start = datetime.combine(day, datetime.min.time())
            top = _top_feature(features, day)
            detections.append(Detection(
                Layer.ML, "ml:isolation_forest", "UNUSUAL_DAY", (meter,),
                start, start + timedelta(days=1), "low", float(score),
                f"{meter} had an unusual day on {day} (most different: {top})",
                start + timedelta(days=1, hours=6),  # daily batch the next morning
            ))
    return detections


def _calendar_explained(data: PlantData, days: pd.Index) -> np.ndarray:
    """Holidays and the day after one are unusual for a known reason; do not report them."""
    kinds = data.day_type.groupby(data.day_type.index.date).first().reindex(days)
    holiday = (kinds == "HOLIDAY").to_numpy()
    return np.asarray(holiday | np.concatenate(([False], holiday[:-1])))


def _top_feature(features: pd.DataFrame, day: object) -> str:
    z = (features.loc[day] - features.mean()) / features.std().replace(0, np.nan)
    context = [c for c in z.index if c.startswith("is_") or c in CONTEXT_FEATURES]
    shape = z.drop(context).abs()
    return str(shape.idxmax()) if shape.notna().any() else "n/a"
