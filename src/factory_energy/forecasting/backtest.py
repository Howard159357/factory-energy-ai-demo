"""Rolling-origin backtest: train on everything before a month, forecast that month, repeat.

Each (model, horizon, month) is one unit of work. Finished units are cached in the database
under a fingerprint of the data and the model, so a second run only re-scores.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from factory_energy.forecasting.features import FEATURE_VERSION, FEATURES, DemandHistory, make_rows
from factory_energy.forecasting.model import (
    TRAINABLE,
    exceedance_probability,
    model_version,
    pinball_loss,
)

HORIZONS = (1, 2, 4, 8, 12, 96)  # 15 min to 3 h ahead (demand control) and day-ahead
SHORT_HORIZONS = (1, 2, 4, 8, 12)
# Two-tier demand-control alerts on P(next-hour demand > contract).
ALERT_LEVELS = {"warning": 0.2, "alarm": 0.5}
MIN_TRAIN_INTERVALS = 30 * 96


@dataclass(frozen=True)
class Unit:
    """One cacheable piece of the backtest."""

    model: str
    horizon: int
    origin: pd.Timestamp  # first day of the test month

    @property
    def key(self) -> tuple[str, int, str]:
        return self.model, self.horizon, f"{self.origin:%Y-%m}"


@dataclass(frozen=True)
class HorizonMetrics:
    model: str
    horizon: int
    samples: int
    mae: float
    mape: float
    wape: float
    rmse: float
    pinball: float
    coverage_80: float
    baseline_name: str
    baseline_mae: float

    @property
    def skill(self) -> float:
        return 1.0 - self.mae / self.baseline_mae if self.baseline_mae else float("nan")


@dataclass(frozen=True)
class AlertEpisode:
    start: datetime
    end: datetime
    peak_kw: float
    first_alert: datetime | None

    @property
    def lead(self) -> timedelta | None:
        return None if self.first_alert is None else self.start - self.first_alert


def fingerprint(history: DemandHistory, model: str) -> str:
    """Changes when the demand data, the features or the model change."""
    digest = hashlib.sha256()
    frame = history.frame
    digest.update(np.round(frame.kw.to_numpy(), 3).tobytes())
    digest.update(np.round(frame.temp_c.to_numpy(), 2).tobytes())
    digest.update(frame.day_type.astype(str).str.cat(sep=",").encode())
    digest.update(frame.overtime.astype(int).to_numpy().tobytes())
    digest.update(f"{FEATURE_VERSION}|{','.join(FEATURES)}|{model}:{model_version(model)}".encode())
    return digest.hexdigest()[:16]


def monthly_origins(index: pd.DatetimeIndex, first_test_month: int) -> list[pd.Timestamp]:
    months = sorted({pd.Timestamp(year=t.year, month=t.month, day=1) for t in index})
    return [m for m in months if m.month >= first_test_month or m.year > months[0].year]


def plan_units(
    history: DemandHistory, models: Sequence[str], horizons: Sequence[int], first_test_month: int
) -> list[Unit]:
    origins = monthly_origins(pd.DatetimeIndex(history.frame.index), first_test_month)
    return [Unit(m, h, o) for h in horizons for o in origins for m in models]


def run_unit(history: DemandHistory, unit: Unit) -> pd.DataFrame:
    """Fit the model on everything before the month and forecast the month."""
    rows = make_rows(history, unit.horizon)
    end = unit.origin + pd.offsets.MonthBegin(1)
    train = rows[rows.index < unit.origin]
    test = rows[(rows.index >= unit.origin) & (rows.index < end)]
    if len(test) == 0 or len(train) < MIN_TRAIN_INTERVALS:
        return pd.DataFrame()
    predicted = TRAINABLE[unit.model](unit.horizon).fit(train).predict(test)
    frame = pd.concat([test[["issue", "y", "last", "same_time_last_week"]], predicted], axis=1)
    frame["horizon"] = unit.horizon
    frame["model"] = unit.model
    return frame.rename_axis("target").reset_index()


def _run_group(history: DemandHistory, units: list[Unit]) -> list[pd.DataFrame]:
    return [run_unit(history, u) for u in units]


def run_units(
    history: DemandHistory,
    units: Sequence[Unit],
    progress: Callable[[str], None] | None = None,
    workers: int = 4,
) -> dict[Unit, pd.DataFrame]:
    """Run units in parallel, one worker per horizon, keeping results keyed by unit."""
    groups: dict[int, list[Unit]] = {}
    for unit in units:
        groups.setdefault(unit.horizon, []).append(unit)
    results: dict[Unit, pd.DataFrame] = {}
    if len(groups) <= 1 or workers <= 1:
        for unit in units:
            if progress:
                progress(f"{unit.model:<9} h={unit.horizon:>2} {unit.origin:%Y-%m}")
            results[unit] = run_unit(history, unit)
        return results
    with ProcessPoolExecutor(max_workers=min(workers, len(groups))) as pool:
        futures = {h: pool.submit(_run_group, history, group) for h, group in groups.items()}
        for h, future in futures.items():
            if progress:
                progress(f"horizon {h:>2}: {len(groups[h])} runs")
            for unit, frame in zip(groups[h], future.result(), strict=True):
                results[unit] = frame
    return results


def add_exceedance(forecasts: pd.DataFrame, contract_kw: float) -> pd.DataFrame:
    out = forecasts.copy()
    out["p_exceed"] = [
        exceedance_probability(a, b, c, contract_kw)
        for a, b, c in zip(out.p10, out.p50, out.p90, strict=True)
    ]
    return out


def with_baselines(forecasts: pd.DataFrame, history: DemandHistory) -> pd.DataFrame:
    """Attach the naive baselines (persistence, same time last week) to stored forecasts."""
    kw = history.kw
    out = forecasts.copy()
    out["last"] = kw.reindex(pd.DatetimeIndex(out.issue)).to_numpy()
    out["same_time_last_week"] = kw.reindex(
        pd.DatetimeIndex(out.target) - pd.Timedelta(days=7)
    ).to_numpy()
    return out.dropna(subset=["last", "same_time_last_week"])


def horizon_metrics(forecasts: pd.DataFrame) -> list[HorizonMetrics]:
    metrics = []
    for (model, horizon), part in forecasts.groupby(["model", "horizon"]):
        h = int(str(horizon))
        error = (part.p50 - part.y).abs()
        busy = part.y > 200  # MAPE is meaningless near zero load
        baseline_name = "same time last week" if h >= 96 else "persistence (last interval)"
        baseline = part.same_time_last_week if h >= 96 else part["last"]
        metrics.append(HorizonMetrics(
            model=str(model),
            horizon=h,
            samples=len(part),
            mae=float(error.mean()),
            mape=float((error[busy] / part.y[busy]).mean()),
            wape=float(error.sum() / part.y.abs().sum()),
            rmse=float(np.sqrt(((part.p50 - part.y) ** 2).mean())),
            pinball=pinball_loss(part.y, part),
            coverage_80=float(((part.y >= part.p10) & (part.y <= part.p90)).mean()),
            baseline_name=baseline_name,
            baseline_mae=float((baseline - part.y).abs().mean()),
        ))
    return metrics


@dataclass(frozen=True)
class PeakMetrics:
    """How well the next-3-hour peak is anticipated: the number a demand controller plans on."""

    model: str
    issues: int
    peak_mae: float  # |predicted 3 h peak - actual 3 h peak|, kW
    peak_bias: float  # predicted - actual, kW (negative = under-forecast)
    peak_time_error_min: float  # median |time of predicted peak - time of actual peak|


def peak_metrics(
    forecasts: pd.DataFrame, horizons: Sequence[int] = SHORT_HORIZONS
) -> list[PeakMetrics]:
    """Per model, compare the highest P50 over the short horizons with the highest actual."""
    short = forecasts[forecasts.horizon.isin(horizons)]
    results = []
    for model, part in short.groupby("model"):
        counts = part.groupby("issue").horizon.nunique()
        complete = counts[counts == len(horizons)].index
        rows = part[part.issue.isin(complete)]
        if rows.empty:
            continue
        predicted = rows.loc[rows.groupby("issue").p50.idxmax(), ["issue", "p50", "target"]]
        actual = rows.loc[rows.groupby("issue").y.idxmax(), ["issue", "y", "target"]]
        merged = predicted.merge(actual, on="issue", suffixes=("_pred", "_act"))
        error = merged.p50 - merged.y
        time_error = (merged.target_pred - merged.target_act).abs().dt.total_seconds() / 60
        results.append(PeakMetrics(str(model), len(merged), float(error.abs().mean()),
                                   float(error.mean()), float(time_error.median())))
    return results


def alert_episodes(
    forecasts: pd.DataFrame, contract_kw: float, threshold: float = 0.5,
    max_horizon: int = 4,  # alerts stay on the next hour; longer horizons are for planning
) -> tuple[list[AlertEpisode], int]:
    """Demand-control view: real exceedance episodes, their earliest alert, and false alarms."""
    short = forecasts[forecasts.horizon <= max_horizon]
    actual = short.drop_duplicates("target").set_index("target").y.sort_index()
    over = actual > contract_kw
    episodes: list[AlertEpisode] = []
    alerts = short[short.p_exceed >= threshold]
    if over.any():
        groups = (over != over.shift()).cumsum()[over]
        for _, members in groups.groupby(groups):
            start, end = members.index[0], members.index[-1] + pd.Timedelta(minutes=15)
            window = alerts[(alerts.target >= start - pd.Timedelta(minutes=15)) &
                            (alerts.target < end)]
            first = window.issue.min() if len(window) else None
            episodes.append(AlertEpisode(
                start.to_pydatetime(), end.to_pydatetime(), float(actual[members.index].max()),
                None if first is None or pd.isna(first) else pd.Timestamp(first).to_pydatetime(),
            ))
    hit_targets = set(actual.index[over])
    near = {t + pd.Timedelta(minutes=15 * k) for t in hit_targets for k in (-2, -1, 0, 1)}
    false_alarm_targets = {t for t in alerts.target if t not in near}
    # Count false alarms as distinct hours so one noisy hour is not counted many times.
    false_alarms = len({pd.Timestamp(t).floor("h") for t in false_alarm_targets})
    return episodes, false_alarms
