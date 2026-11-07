"""Read-only queries for the dashboard.

The plant database is attached read-only to a private in-memory DuckDB. At start-up a few
compact tables are built once so that every replay tick touches only small, well-ordered data:

- ``plant_minute`` / ``plant_interval``: plant kW per minute and per demand interval.
- ``meter_hour``: kWh per meter per hour, for energy rankings and 24 h totals.
- ``reading_window``: every meter's minute readings inside the scenario replay windows,
  ordered by time so a point-in-time snapshot reads one row group instead of the whole year.
- detections are loaded into a sorted frame and sliced by detection time.
"""

from __future__ import annotations

import json
import threading
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from factory_energy.anomaly.evaluate import Score, Truth, evaluate
from factory_energy.anomaly.models import Detection, Layer
from factory_energy.forecasting.backtest import (
    ALERT_LEVELS,
    HorizonMetrics,
    PeakMetrics,
    alert_episodes,
    horizon_metrics,
    peak_metrics,
)
from factory_energy.forecasting.model import PRIMARY_MODEL

INTERVAL = timedelta(minutes=15)
WINDOW_PAD_BEFORE = timedelta(days=8)  # evidence charts look back up to a week
WINDOW_PAD_AFTER = timedelta(days=1)
DETECTION_COLUMNS = [
    "detection_id", "layer", "detector", "event_type", "meter_ids", "start_ts", "end_ts",
    "detected_ts", "severity", "score", "message",
]


@dataclass(frozen=True)
class ScenarioInfo:
    scenario_id: str
    title: str
    caption: str
    description: str
    replay_start: datetime
    replay_end: datetime
    what_if: dict[str, float]


class DashboardData:
    def __init__(self, database: str | Path, contract_kw: float = 0.0) -> None:
        self._contract_kw = contract_kw
        path = Path(database)
        self.database = path
        if not path.exists():
            raise FileNotFoundError(f"{path} not found; run `build-demo` first")
        self._lock = threading.Lock()
        self._db = duckdb.connect(":memory:")
        location = path.as_posix().replace("'", "''")  # ATTACH takes no bind parameters
        self._db.execute(f"ATTACH '{location}' AS plant (READ_ONLY)")
        self._db.execute("USE plant")
        self.meters = self.query("SELECT * FROM meter_master ORDER BY meter_id").set_index(
            "meter_id"
        )
        self.has_detections = self._has_table("detections")
        self.has_forecasts = self._has_table("forecasts") and self._has_column("forecasts", "model")
        self._build_aggregates()
        bounds = self.query("SELECT MIN(ts) lo, MAX(ts) hi FROM plant_minute")
        if bounds.empty or pd.isna(bounds.lo[0]):
            raise ValueError("database has no readings")
        self.first_ts: datetime = _dt(bounds.lo[0])
        self.last_ts: datetime = _dt(bounds.hi[0])
        self._scenarios = self._load_scenarios()
        self._coverage = self._build_reading_window()
        self._detections = self._load_detections()
        self._detected_at = self._detections.detected_ts.to_numpy()
        self.seed = self._load_seed()

    # -- plumbing ---------------------------------------------------------------------------
    def query(self, sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
        with self._lock:
            return self._db.execute(sql, params).df()

    def _has_column(self, table: str, column: str) -> bool:
        rows = self.query(
            "SELECT COUNT(*) n FROM information_schema.columns WHERE table_name = ? "
            "AND column_name = ?", (table, column),
        )
        return bool(rows.n[0])

    def _has_table(self, name: str) -> bool:
        rows = self.query(
            "SELECT COUNT(*) n FROM information_schema.tables WHERE table_name = ?", (name,)
        )
        return bool(rows.n[0])

    def _build_aggregates(self) -> None:
        with self._lock:
            self._db.execute("""
                CREATE TEMP TABLE plant_minute AS
                SELECT r.ts, SUM(r.kw) AS kw FROM meter_reading_minute r
                JOIN meter_master m USING (meter_id)
                WHERE m.include_in_plant_total AND m.enabled
                GROUP BY r.ts ORDER BY r.ts""")
            self._db.execute("""
                CREATE TEMP TABLE plant_interval AS
                SELECT time_bucket(INTERVAL 15 MINUTE, ts) AS w, AVG(kw) AS kw, COUNT(*) AS n
                FROM plant_minute GROUP BY 1 ORDER BY 1""")
            self._db.execute("""
                CREATE TEMP TABLE meter_hour AS
                SELECT meter_id, date_trunc('hour', ts) AS h, SUM(kw) / 60 AS kwh
                FROM meter_reading_minute GROUP BY 1, 2 ORDER BY 2, 1""")

    def _build_reading_window(self) -> list[tuple[datetime, datetime]]:
        """Copy the replay windows' readings into a time-ordered table; return the coverage."""
        spans = [
            (max(s.replay_start - WINDOW_PAD_BEFORE, self.first_ts),
             min(s.replay_end + WINDOW_PAD_AFTER, self.last_ts))
            for s in self._scenarios
        ] or [(self.first_ts, min(self.first_ts + timedelta(days=14), self.last_ts))]
        spans.sort()
        merged: list[tuple[datetime, datetime]] = []
        for lo, hi in spans:
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        condition = " OR ".join("(ts >= ? AND ts <= ?)" for _ in merged)
        params = tuple(v for span in merged for v in span)
        with self._lock:
            self._db.execute(
                "CREATE TEMP TABLE reading_window AS SELECT ts, meter_id, kw, pf "
                f"FROM meter_reading_minute WHERE {condition} ORDER BY ts, meter_id", params,
            )
        return merged

    def _covered(self, start: datetime, end: datetime) -> bool:
        return any(lo <= start and end <= hi for lo, hi in self._coverage)

    def _load_detections(self) -> pd.DataFrame:
        if not self.has_detections:
            return pd.DataFrame(columns=DETECTION_COLUMNS)
        frame = self.query("SELECT * FROM detections ORDER BY detected_ts, detection_id")
        frame["meter_ids"] = frame.meter_ids.map(tuple)
        return frame

    def _load_scenarios(self) -> list[ScenarioInfo]:
        if not self._has_table("scenarios"):
            return []
        rows = self.query("SELECT * FROM scenarios ORDER BY replay_start")
        return [
            ScenarioInfo(r.scenario_id, r.title, str(getattr(r, "caption", "") or r.title),
                         r.description, _dt(r.replay_start), _dt(r.replay_end),
                         json.loads(r.what_if))
            for r in rows.itertuples()
        ]

    def _load_seed(self) -> int:
        if not self._has_table("simulation_runs"):
            return 42
        rows = self.query("SELECT seed FROM simulation_runs ORDER BY created_at DESC LIMIT 1")
        return 42 if rows.empty else int(rows.seed[0])

    # -- metadata ---------------------------------------------------------------------------
    @property
    def feeder_ids(self) -> list[str]:
        mask = (self.meters.meter_type == "FEEDER") & self.meters.enabled
        return list(self.meters.index[mask])

    @property
    def equipment_ids(self) -> list[str]:
        return list(self.meters.index[self.meters.meter_type == "EQUIPMENT"])

    def name(self, meter_id: str) -> str:
        if meter_id in self.meters.index:
            return str(self.meters.at[meter_id, "display_name"])
        return meter_id

    def scenarios(self) -> list[ScenarioInfo]:
        return list(self._scenarios)

    def highlight(self, scenario_id: str, start: datetime, end: datetime) -> datetime | None:
        """The moment worth jumping to: the first high-severity label, else the first rule or
        baseline detection inside the replay window, else the first label."""
        high = self.query(
            "SELECT MIN(start_ts) t FROM ground_truth_events WHERE scenario_id = ? "
            "AND severity = 'high'", (scenario_id,),
        ).t[0]
        if not pd.isna(high):
            return _dt(high)
        if self.has_detections:
            inside = self._detections[
                (self._detections.layer != "ML")
                & (self._detections.detected_ts >= start) & (self._detections.detected_ts < end)
            ]
            if len(inside):
                return _dt(inside.detected_ts.iloc[0])
        first = self.query(
            "SELECT MIN(start_ts) t FROM ground_truth_events WHERE scenario_id = ?",
            (scenario_id,),
        ).t[0]
        return None if pd.isna(first) else _dt(first)

    # -- time series ------------------------------------------------------------------------
    def plant_series(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Plant kW per minute for start <= ts < end."""
        return self.query(
            "SELECT ts, kw FROM plant_minute WHERE ts >= ? AND ts < ? ORDER BY ts", (start, end)
        )

    def demand(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Completed demand intervals ending at or before `end`."""
        return self.query(
            "SELECT w, kw FROM plant_interval WHERE w >= ? AND w + INTERVAL 15 MINUTE <= ? "
            "ORDER BY w", (start, end),
        )

    def snapshot(self, as_of: datetime) -> pd.DataFrame:
        """Latest reading of every meter at `as_of`, indexed by meter_id."""
        table = "reading_window" if self._covered(as_of, as_of) else "meter_reading_minute"
        frame = self.query(f"SELECT meter_id, kw, pf FROM {table} WHERE ts = ?", (as_of,))
        return frame.set_index("meter_id").reindex(self.meters.index)

    def meter_series(self, meter_ids: list[str], start: datetime, end: datetime) -> pd.DataFrame:
        if not meter_ids:
            return pd.DataFrame()
        table = "reading_window" if self._covered(start, end) else "meter_reading_minute"
        marks = ",".join("?" for _ in meter_ids)
        frame = self.query(
            f"SELECT ts, meter_id, kw FROM {table} WHERE meter_id IN ({marks}) "
            "AND ts >= ? AND ts <= ?", (*meter_ids, start, end),
        )
        return frame.pivot(index="ts", columns="meter_id", values="kw").sort_index()

    def temperature(self, as_of: datetime) -> float | None:
        rows = self.query("SELECT temp_c FROM weather_minute WHERE ts = ?", (as_of,))
        return None if rows.empty else float(rows.temp_c[0])

    def energy_kwh(self, start: datetime, end: datetime) -> float:
        rows = self.query(
            "SELECT COALESCE(SUM(kw), 0) / 60 e FROM plant_minute WHERE ts >= ? AND ts < ?",
            (start, end),
        )
        return float(rows.e[0])

    def meter_energy(self, start: datetime, end: datetime) -> pd.Series:
        """kWh per equipment meter over whole hours in [start, end), from the hourly table."""
        meters = self.equipment_ids
        marks = ",".join("?" for _ in meters)
        frame = self.query(
            f"SELECT meter_id, SUM(kwh) kwh FROM meter_hour WHERE meter_id IN ({marks}) "
            "AND h >= ? AND h < ? GROUP BY 1", (*meters, start, end),
        )
        return frame.set_index("meter_id").kwh.reindex(meters).fillna(0.0)

    # -- detections and forecasts -----------------------------------------------------------
    def detections(self, until: datetime, since: datetime | None = None) -> pd.DataFrame:
        """Detections known by `until` (by detection time), newest first."""
        hi = bisect_right(self._detected_at, np.datetime64(until))
        lo = bisect_right(self._detected_at, np.datetime64(since)) if since else 0
        return self._detections.iloc[lo:hi][::-1]

    def next_forecast(
        self, as_of: datetime, max_minutes: int = 60, model: str = PRIMARY_MODEL
    ) -> pd.DataFrame:
        """Forecasts issued at the latest completed interval, up to `max_minutes` ahead."""
        if not self.has_forecasts:
            return pd.DataFrame(columns=["target_ts", "horizon_min", "p10", "p50", "p90",
                                         "p_exceed"])
        issue = interval_floor(as_of) - INTERVAL  # start of the last completed interval
        return self.query(
            "SELECT target_ts, horizon_min, p10, p50, p90, p_exceed FROM forecasts "
            "WHERE issue_ts = ? AND horizon_min <= ? AND model = ? ORDER BY target_ts",
            (issue, max_minutes, model),
        )

    def next_hour_forecast(self, as_of: datetime) -> pd.DataFrame:
        return self.next_forecast(as_of, 60)

    def day_ahead(self, day: date, model: str = PRIMARY_MODEL) -> pd.DataFrame:
        if not self.has_forecasts:
            return pd.DataFrame()
        start = datetime.combine(day, datetime.min.time())
        return self.query(
            "SELECT target_ts, p10, p50, p90, p_exceed FROM forecasts WHERE horizon_min = 1440 "
            "AND model = ? AND target_ts >= ? AND target_ts < ? ORDER BY target_ts",
            (model, start, start + timedelta(days=1)),
        )

    def models(self) -> list[str]:
        if not self.has_forecasts:
            return []
        rows = self.query("SELECT DISTINCT model FROM forecasts ORDER BY 1")
        return [str(m) for m in rows.model]

    def exceedance_timeline(self, start: datetime, until: datetime) -> pd.DataFrame:
        """Highest next-hour exceedance probability seen at each issue time."""
        if not self.has_forecasts:
            return pd.DataFrame(columns=["issue_ts", "p"])
        return self.query(
            "SELECT issue_ts, MAX(p_exceed) p FROM forecasts WHERE horizon_min <= 60 "
            "AND model = ? AND issue_ts >= ? AND issue_ts <= ? GROUP BY 1 ORDER BY 1",
            (PRIMARY_MODEL, start, until),
        )

    # -- whole-run summaries (computed once by the context) ---------------------------------
    def forecast_metrics(self) -> list[HorizonMetrics]:
        if not self.has_forecasts:
            return []
        frame = self.query(
            'SELECT issue_ts AS issue, target_ts AS "target", horizon_min, p10, p50, p90, '
            "actual AS y, model FROM forecasts"
        )
        frame["horizon"] = frame.horizon_min // 15
        history = self.query("SELECT w, kw FROM plant_interval").set_index("w").kw
        frame["last"] = history.reindex(frame.issue).to_numpy()  # demand at issue time
        frame["same_time_last_week"] = history.reindex(
            frame.target - pd.Timedelta(days=7)
        ).to_numpy()
        return horizon_metrics(frame.dropna(subset=["last", "same_time_last_week"]))

    def alert_leads(self) -> dict[str, list[str]]:
        """Alarm lead per exceedance episode, per model, from the stored backtest."""
        if not self.has_forecasts:
            return {}
        frame = self.query(
            'SELECT issue_ts AS issue, target_ts AS "target", horizon_min / 15 AS horizon, '
            "p_exceed, actual AS y, model FROM forecasts WHERE horizon_min <= 60"
        )
        frame["horizon"] = frame.horizon.astype(int)
        contract = self._contract_kw
        leads: dict[str, list[str]] = {}
        for model, part in frame.groupby("model"):
            episodes, _ = alert_episodes(part, contract, ALERT_LEVELS["alarm"])
            leads[str(model)] = [
                "-" if e.lead is None else f"{e.lead.total_seconds() / 60:.0f}" for e in episodes
            ]
        return leads

    def peak_metrics(self) -> list[PeakMetrics]:
        if not self.has_forecasts:
            return []
        frame = self.query(
            'SELECT issue_ts AS issue, target_ts AS "target", horizon_min / 15 AS horizon, p50, '
            "actual AS y, model FROM forecasts WHERE horizon_min <= 180"
        )
        frame["horizon"] = frame.horizon.astype(int)
        return peak_metrics(frame)

    def forecast_period(self) -> tuple[datetime, datetime] | None:
        if not self.has_forecasts:
            return None
        rows = self.query("SELECT MIN(target_ts) lo, MAX(target_ts) hi FROM forecasts")
        return None if rows.empty or pd.isna(rows.lo[0]) else (_dt(rows.lo[0]), _dt(rows.hi[0]))

    def detection_scores(self) -> list[Score]:
        if not self.has_detections:
            return []
        truths = [
            Truth(r.event_id, r.event_type, tuple(r.meter_ids), _dt(r.start_ts), _dt(r.end_ts))
            for r in self.query("SELECT * FROM ground_truth_events").itertuples()
        ]
        detections = [
            Detection(Layer(r.layer), r.detector, r.event_type, tuple(r.meter_ids),
                      _dt(r.start_ts), _dt(r.end_ts), r.severity, float(r.score), r.message,
                      _dt(r.detected_ts))
            for r in self._detections.itertuples()
        ]
        return evaluate(detections, truths)

    def weekday_hour_profile(self) -> pd.DataFrame:
        return self.query(
            "SELECT isodow(ts) - 1 AS weekday, hour(ts) AS hour, AVG(kw) AS kw "
            "FROM plant_minute GROUP BY 1, 2 ORDER BY 1, 2"
        )

    def monthly_energy(self) -> pd.DataFrame:
        feeders = self.feeder_ids
        marks = ",".join("?" for _ in feeders)
        return self.query(
            f"SELECT date_trunc('month', h) AS month, meter_id, SUM(kwh) / 1000 AS mwh "
            f"FROM meter_hour WHERE meter_id IN ({marks}) GROUP BY 1, 2 ORDER BY 1, 2",
            tuple(feeders),
        )


def _dt(value: Any) -> datetime:
    result: datetime = pd.Timestamp(value).to_pydatetime()
    return result


def interval_floor(ts: datetime, minutes: int = 15) -> datetime:
    """Start of the demand interval that contains `ts`."""
    floored = ts.replace(second=0, microsecond=0)
    return floored - timedelta(minutes=floored.minute % minutes)
