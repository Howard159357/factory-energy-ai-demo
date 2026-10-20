from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb
import pandas as pd

from factory_energy.config.models import FactorySettings
from factory_energy.forecasting.backtest import (
    ALERT_LEVELS,
    HORIZONS,
    AlertEpisode,
    HorizonMetrics,
    PeakMetrics,
    Unit,
    add_exceedance,
    alert_episodes,
    fingerprint,
    horizon_metrics,
    peak_metrics,
    plan_units,
    run_units,
    with_baselines,
)
from factory_energy.forecasting.features import DemandHistory, load_history
from factory_energy.forecasting.model import (
    ENSEMBLE,
    ENSEMBLE_MEMBERS,
    MODELS,
    PRIMARY_MODEL,
    TRAINABLE,
    ensemble_of,
)
from factory_energy.storage.schema import initialize_schema


@dataclass(frozen=True)
class ForecastReport:
    metrics: list[HorizonMetrics]
    peaks: list[PeakMetrics]
    alerts: dict[str, dict[str, tuple[list[AlertEpisode], int]]]  # model -> level -> ...
    units_total: int
    units_reused: int
    primary: str = PRIMARY_MODEL


def _columns(connection: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = connection.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
    ).fetchall()
    return {r[0] for r in rows}


def ensure_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the forecast tables, replacing an older single-model layout if present.

    The old layout had no `forecast_runs` table and keyed forecasts without the model, so a
    `forecasts` table that exists before `forecast_runs` does is the old one.
    """
    if _columns(connection, "forecasts") and "model" not in _primary_key(connection, "forecasts"):
        connection.execute("DROP TABLE forecasts")
        connection.execute("DROP TABLE IF EXISTS forecast_runs")
    initialize_schema(connection)


def _primary_key(connection: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = connection.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'", (table,),
    ).fetchall()
    return {column for row in rows for column in row[0]}


def cached_units(connection: duckdb.DuckDBPyConnection) -> dict[tuple[str, int, str], str]:
    rows = connection.execute(
        "SELECT model, horizon_min, origin_month, fingerprint FROM forecast_runs"
    ).fetchall()
    return {(r[0], int(r[1]) // 15, r[2]): r[3] for r in rows}


def load_forecasts(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    frame = connection.execute(
        'SELECT issue_ts AS issue, target_ts AS "target", horizon_min / 15 AS horizon, p10, p50, '
        "p90, p_exceed, actual AS y, model FROM forecasts"
    ).df()
    frame["horizon"] = frame.horizon.astype(int)
    return frame


def store_unit(
    connection: duckdb.DuckDBPyConnection, unit: Unit, frame: pd.DataFrame, print_: str
) -> None:
    connection.execute(
        "DELETE FROM forecasts WHERE model = ? AND horizon_min = ? AND target_ts >= ? "
        "AND target_ts < ?",
        (unit.model, unit.horizon * 15, unit.origin, unit.origin + pd.offsets.MonthBegin(1)),
    )
    if len(frame):
        out = frame[["issue", "target", "horizon", "p10", "p50", "p90", "p_exceed", "y", "model"]]
        connection.register("forecast_frame", out.assign(horizon=out.horizon * 15))
        connection.execute(
            "INSERT INTO forecasts SELECT issue, target, horizon, p10, p50, p90, p_exceed, y, "
            "model FROM forecast_frame"
        )
        connection.unregister("forecast_frame")
    connection.execute(
        "INSERT OR REPLACE INTO forecast_runs VALUES (?, ?, ?, ?, ?, ?)",
        (unit.model, unit.horizon * 15, unit.key[2], print_, len(frame),
         datetime.now(UTC).replace(tzinfo=None)),
    )


def run_forecasting(
    connection: duckdb.DuckDBPyConnection,
    settings: FactorySettings,
    progress: Callable[[str], None] | None = None,
    models: Sequence[str] = tuple(MODELS),
    refresh: bool = False,
    workers: int = 4,
) -> ForecastReport:
    """Backtest every model; reuse cached (model, horizon, month) runs whose fingerprint matches."""
    ensure_tables(connection)
    history: DemandHistory = load_history(connection, settings.demand.interval_minutes)
    contract = settings.demand.contract_capacity_kw
    trainable = [m for m in models if m in TRAINABLE]
    if ENSEMBLE in models:
        trainable += [m for m in ENSEMBLE_MEMBERS if m not in trainable]
    prints = {m: fingerprint(history, m) for m in (*trainable, ENSEMBLE)}
    units = plan_units(history, trainable, HORIZONS, first_test_month=6)
    cached = {} if refresh else cached_units(connection)
    todo = [u for u in units if cached.get(u.key) != prints[u.model]]
    reused = len(units) - len(todo)
    results = run_units(history, todo, progress, workers)
    for unit, frame in results.items():
        store_unit(connection, unit, add_exceedance(frame, contract) if len(frame) else frame,
                   prints[unit.model])
    forecasts = load_forecasts(connection)
    if ENSEMBLE in models:  # averaged from the stored members, never refitted
        ensemble_units = plan_units(history, [ENSEMBLE], HORIZONS, first_test_month=6)
        units += ensemble_units
        for unit in ensemble_units:
            if cached.get(unit.key) == prints[ENSEMBLE]:
                reused += 1
                continue
            end = unit.origin + pd.offsets.MonthBegin(1)
            members = [
                forecasts[(forecasts.model == m) & (forecasts.horizon == unit.horizon)
                          & (forecasts.target >= unit.origin) & (forecasts.target < end)]
                for m in ENSEMBLE_MEMBERS
            ]
            frame = ensemble_of(members) if all(len(m) for m in members) else pd.DataFrame()
            store_unit(connection, unit, add_exceedance(frame, contract) if len(frame) else frame,
                       prints[ENSEMBLE])
        forecasts = load_forecasts(connection)
    if progress:
        progress(f"{reused} of {len(units)} backtest runs reused from cache")
    forecasts = forecasts[forecasts.model.isin(models)]
    alerts = {
        model: {
            level: alert_episodes(forecasts[forecasts.model == model], contract, threshold)
            for level, threshold in ALERT_LEVELS.items()
        }
        for model in models
    }
    scored = with_baselines(forecasts, history)
    return ForecastReport(horizon_metrics(scored), peak_metrics(forecasts), alerts, len(units),
                          reused)
