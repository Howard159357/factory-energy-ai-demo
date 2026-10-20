"""Forecast models that all speak the same language: P10 / P50 / P90 of the target.

Every model is fitted on `make_rows` output and predicts the change from an anchor (the last
completed interval for short horizons, the same time last week for day-ahead). Bands are then
widened on a held-out fortnight until they cover 80% of outcomes, the same way for every model,
so the comparison is about the point forecast and the shape of the uncertainty, not about
tuning tricks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import erf, sqrt
from typing import Any, Protocol

import numpy as np
import pandas as pd

from factory_energy.forecasting.features import FEATURES, INTERVALS_PER_DAY

QUANTILES = (0.1, 0.5, 0.9)
NAMES = [f"p{round(q * 100)}" for q in QUANTILES]
Z90 = 1.2815515655446004  # standard normal 90th percentile
CALIBRATION_DAYS = 14
TARGET_COVERAGE = 0.8
MAX_WIDTH_FACTOR = 6.0  # a band that needs more than this is a broken model, not a wide one
MIN_HALF_BAND_KW = 5.0
PRIMARY_MODEL = "lightgbm"  # the model the dashboard shows and the alerts use
PROFILE_WEEKS = 4


def anchor(rows: pd.DataFrame, horizon: int) -> pd.Series:
    """What the forecast is expressed relative to.

    Trees cannot predict values outside the range they were trained on, and the plant has
    never been above its contract in training. Predicting the *change* from a recent value
    lets a hot afternoon that is already running high be carried past the limit.
    """
    column = "same_time_last_week" if horizon >= INTERVALS_PER_DAY else "last"
    return rows[column]


class Forecaster(Protocol):
    name: str
    version: str  # bump when the model's behaviour changes, to invalidate cached runs

    def fit(self, rows: pd.DataFrame) -> Forecaster: ...
    def predict(self, rows: pd.DataFrame) -> pd.DataFrame: ...


def _calibrated(model: Any, rows: pd.DataFrame) -> None:
    """Fit on all but the last fortnight, then widen the bands to 80% coverage on it."""
    cutoff = rows.index.max() - pd.Timedelta(days=CALIBRATION_DAYS)
    train, calibration = rows[rows.index <= cutoff], rows[rows.index > cutoff]
    model.width_factor = 1.0
    model._fit_raw(train)
    if len(calibration):
        raw = model.predict(calibration)
        lower = (raw.p50 - raw.p10).clip(lower=1e-6)
        upper = (raw.p90 - raw.p50).clip(lower=1e-6)
        y = calibration.y
        needed = np.where(y >= raw.p50, (y - raw.p50) / upper, (raw.p50 - y) / lower)
        model.width_factor = min(max(1.0, float(np.quantile(needed, TARGET_COVERAGE))),
                                 MAX_WIDTH_FACTOR)


def residual_offsets(residual: np.ndarray) -> tuple[float, float]:
    """Empirical 10% / 90% residual quantiles, never narrower than a few kW."""
    low, high = float(np.quantile(residual, 0.1)), float(np.quantile(residual, 0.9))
    return min(low, -MIN_HALF_BAND_KW), max(high, MIN_HALF_BAND_KW)


def _widen(raw: np.ndarray, factor: float) -> np.ndarray:
    raw.sort(axis=1)  # no quantile crossing
    median = raw[:, 1:2]
    return np.asarray(median + (raw - median) * factor)


@dataclass
class LightGBMForecaster:
    """Gradient-boosted quantile regression on the change from the anchor."""

    horizon: int
    name: str = "lightgbm"
    version: str = "2"
    n_estimators: int = 300
    learning_rate: float = 0.05
    seed: int = 0
    width_factor: float = 1.0
    models: dict[float, Any] = field(default_factory=dict)

    def _fit_raw(self, rows: pd.DataFrame) -> None:
        from lightgbm import LGBMRegressor

        delta = rows.y - anchor(rows, self.horizon)
        for q in QUANTILES:
            model = LGBMRegressor(
                objective="quantile", alpha=q, n_estimators=self.n_estimators,
                learning_rate=self.learning_rate, num_leaves=31, min_child_samples=20,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
                random_state=self.seed, verbose=-1, deterministic=True, force_row_wise=True,
            )
            self.models[q] = model.fit(rows[FEATURES], delta)

    def fit(self, rows: pd.DataFrame) -> LightGBMForecaster:
        _calibrated(self, rows)
        return self

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        base = anchor(rows, self.horizon).to_numpy()
        raw = np.column_stack([self.models[q].predict(rows[FEATURES]) for q in QUANTILES])
        return pd.DataFrame(_widen(raw, self.width_factor) + base[:, None], index=rows.index,
                            columns=NAMES)


@dataclass
class LinearForecaster:
    """Ridge regression on the same features; bands from the empirical residual quantiles.

    The interpretable yardstick: if the trees are not clearly better than this, the
    non-linearity is not earning its keep.
    """

    horizon: int
    name: str = "linear"
    version: str = "3"
    alpha: float = 10.0
    width_factor: float = 1.0
    model: Any = None
    scaler: Any = None
    offsets: tuple[float, float] = (0.0, 0.0)  # residual quantiles 10% and 90%

    def _fit_raw(self, rows: pd.DataFrame) -> None:
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler

        delta = (rows.y - anchor(rows, self.horizon)).to_numpy()
        self.scaler = StandardScaler().fit(rows[FEATURES].to_numpy())
        x = self.scaler.transform(rows[FEATURES].to_numpy())
        self.model = Ridge(alpha=self.alpha).fit(x, delta)
        residual = delta - self.model.predict(x)
        self.offsets = residual_offsets(residual)

    def fit(self, rows: pd.DataFrame) -> LinearForecaster:
        _calibrated(self, rows)
        return self

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        base = anchor(rows, self.horizon).to_numpy()
        median = self.model.predict(self.scaler.transform(rows[FEATURES].to_numpy()))
        raw = np.column_stack([median + self.offsets[0], median, median + self.offsets[1]])
        return pd.DataFrame(_widen(raw, self.width_factor) + base[:, None], index=rows.index,
                            columns=NAMES)


@dataclass
class HistGradientBoostingForecaster:
    """scikit-learn's histogram gradient boosting with a quantile loss: same idea as LightGBM,
    different implementation and no extra dependency. Agreement between the two is a useful
    check that the result is not an artefact of one library."""

    horizon: int
    name: str = "hgb"
    version: str = "1"
    max_iter: int = 180
    learning_rate: float = 0.05
    seed: int = 0
    width_factor: float = 1.0
    models: dict[float, Any] = field(default_factory=dict)

    def _fit_raw(self, rows: pd.DataFrame) -> None:
        from sklearn.ensemble import HistGradientBoostingRegressor

        delta = rows.y - anchor(rows, self.horizon)
        for q in QUANTILES:
            model = HistGradientBoostingRegressor(
                loss="quantile", quantile=q, max_iter=self.max_iter,
                learning_rate=self.learning_rate, max_leaf_nodes=31, l2_regularization=1.0,
                random_state=self.seed,
            )
            self.models[q] = model.fit(rows[FEATURES].to_numpy(), delta.to_numpy())

    def fit(self, rows: pd.DataFrame) -> HistGradientBoostingForecaster:
        _calibrated(self, rows)
        return self

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        base = anchor(rows, self.horizon).to_numpy()
        x = rows[FEATURES].to_numpy()
        raw = np.column_stack([self.models[q].predict(x) for q in QUANTILES])
        return pd.DataFrame(_widen(raw, self.width_factor) + base[:, None], index=rows.index,
                            columns=NAMES)


@dataclass
class ProfileForecaster:
    """The plant's own habit: median of the same weekday-type and time slot over recent weeks,
    nudged by how far the plant currently sits from its profile.

    This is what an energy manager does with a spreadsheet, and it is the honest floor any
    learned model has to beat.
    """

    horizon: int
    name: str = "profile"
    version: str = "2"
    width_factor: float = 1.0
    table: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    offsets: tuple[float, float] = (0.0, 0.0)

    @staticmethod
    def _keys(rows: pd.DataFrame) -> pd.MultiIndex:
        kind = np.where(rows.is_workday > 0, "W", np.where(rows.is_saturday > 0, "S", "R"))
        return pd.MultiIndex.from_arrays([kind, rows.slot.astype(int)], names=["kind", "slot"])

    def _profile(self, rows: pd.DataFrame) -> np.ndarray:
        looked_up = self.table.reindex(self._keys(rows)).to_numpy()
        return np.asarray(np.where(np.isnan(looked_up), rows.same_time_last_week, looked_up))

    def _fit_raw(self, rows: pd.DataFrame) -> None:
        recent = rows[rows.index > rows.index.max() - pd.Timedelta(weeks=PROFILE_WEEKS)]
        self.table = recent.y.groupby(self._keys(recent)).median()
        residual = (rows.y - self._point(rows)).to_numpy()
        self.offsets = residual_offsets(residual)

    def _point(self, rows: pd.DataFrame) -> np.ndarray:
        profile = self._profile(rows)
        # The deviation seen at issue time fades with lead time (about an hour).
        issue_profile = np.roll(profile, self.horizon) if self.horizon < len(rows) else profile
        deviation = rows["last"].to_numpy() - issue_profile
        return np.asarray(profile + deviation * np.exp(-self.horizon / 4.0))

    def fit(self, rows: pd.DataFrame) -> ProfileForecaster:
        _calibrated(self, rows)
        return self

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        median = self._point(rows)
        raw = np.column_stack([median + self.offsets[0], median, median + self.offsets[1]])
        return pd.DataFrame(_widen(raw, self.width_factor), index=rows.index, columns=NAMES)


ENSEMBLE = "ensemble"
ENSEMBLE_MEMBERS = ("lightgbm", "linear")
ENSEMBLE_VERSION = "1"


def ensemble_of(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Quantile-wise average of member forecasts for the same targets (no refitting)."""
    aligned = [f.set_index("target").sort_index() for f in frames]
    base = aligned[0]
    stacked = np.mean([f.loc[base.index, NAMES].to_numpy() for f in aligned], axis=0)
    stacked.sort(axis=1)
    out = base.copy()
    out[NAMES] = stacked
    out["model"] = ENSEMBLE
    return out.reset_index()


TRAINABLE: dict[str, Callable[[int], Any]] = {
    "profile": ProfileForecaster,
    "linear": LinearForecaster,
    "hgb": HistGradientBoostingForecaster,
    "lightgbm": LightGBMForecaster,
}
MODELS: tuple[str, ...] = (*TRAINABLE, ENSEMBLE)


def model_version(name: str) -> str:
    if name == ENSEMBLE:
        members = "+".join(f"{m}:{TRAINABLE[m](1).version}" for m in ENSEMBLE_MEMBERS)
        return f"{ENSEMBLE_VERSION}({members})"
    return str(TRAINABLE[name](1).version)


def exceedance_probability(p10: float, p50: float, p90: float, limit: float) -> float:
    """P(demand > limit), approximating the forecast distribution as a two-piece normal."""
    sigma = (p90 - p50 if limit >= p50 else p50 - p10) / Z90
    if sigma <= 0:
        return 1.0 if p50 > limit else 0.0
    z = (limit - p50) / sigma
    return 0.5 * (1.0 - erf(z / sqrt(2.0)))


def pinball_loss(y: pd.Series, predicted: pd.DataFrame) -> float:
    """Mean pinball loss over the three quantiles: the standard score for quantile forecasts."""
    total = 0.0
    for q, name in zip(QUANTILES, NAMES, strict=True):
        diff = y.to_numpy() - predicted[name].to_numpy()
        total += float(np.mean(np.maximum(q * diff, (q - 1) * diff)))
    return total / len(QUANTILES)
