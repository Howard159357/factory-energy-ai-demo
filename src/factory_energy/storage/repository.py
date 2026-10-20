from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import duckdb

from factory_energy.config.models import MeterCatalog, MeterType
from factory_energy.storage.models import MinuteReading

METRICS = frozenset({"kwh", "kw", "pf", "r_v", "s_v", "t_v", "r_a", "s_a", "t_a"})


class LocalRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def load_meter_master(self, catalog: MeterCatalog) -> None:
        rows: list[tuple[Any, ...]] = [
            (f.meter_id, f.name, MeterType.FEEDER.value, None, None, f.rated_kw, True, f.enabled)
            for f in catalog.feeders
        ]
        rows += [
            (e.meter_id, e.name, MeterType.EQUIPMENT.value, e.feeder, e.category, e.rated_kw,
             False, e.enabled)
            for e in catalog.equipment
        ]
        self.connection.executemany(
            "INSERT OR REPLACE INTO meter_master VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
        )

    def insert_minute_batch(self, readings: Sequence[MinuteReading]) -> None:
        """Idempotent upsert keyed on (meter_id, ts)."""
        self.connection.executemany(
            "INSERT OR REPLACE INTO meter_reading_minute VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [reading.as_row() for reading in readings],
        )

    def latest_timestamp(self, meter_id: str) -> datetime | None:
        row = self.connection.execute(
            "SELECT MAX(ts) FROM meter_reading_minute WHERE meter_id = ?", (meter_id,)
        ).fetchone()
        return row[0] if row else None

    def meter_series(
        self, meter_ids: Sequence[str], start: datetime, end: datetime, metric: str = "kw"
    ) -> list[tuple[Any, ...]]:
        if metric not in METRICS or not meter_ids:
            raise ValueError("unsupported metric or empty meter list")
        placeholders = ",".join("?" for _ in meter_ids)
        return self.connection.execute(
            f"SELECT meter_id, ts, {metric} FROM meter_reading_minute "
            f"WHERE meter_id IN ({placeholders}) AND ts >= ? AND ts < ? ORDER BY ts, meter_id",
            (*meter_ids, start, end),
        ).fetchall()
