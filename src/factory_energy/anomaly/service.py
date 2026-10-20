from __future__ import annotations

import duckdb

from factory_energy.anomaly.baseline import baseline_drift
from factory_energy.anomaly.data import PlantData, load_plant_data
from factory_energy.anomaly.evaluate import Score, Truth, evaluate
from factory_energy.anomaly.models import Detection
from factory_energy.anomaly.rules import run_rules
from factory_energy.config.models import FactorySettings
from factory_energy.storage.schema import initialize_schema


def detect_all(data: PlantData, use_ml: bool = True) -> list[Detection]:
    detections = [*run_rules(data), *baseline_drift(data)]
    if use_ml:
        from factory_energy.anomaly.ml import isolation_forest

        detections += isolation_forest(data)
    return sorted(detections, key=lambda d: (d.start, d.detector))


def load_truths(connection: duckdb.DuckDBPyConnection) -> list[Truth]:
    rows = connection.execute(
        "SELECT event_id, event_type, meter_ids, start_ts, end_ts FROM ground_truth_events"
    ).fetchall()
    return [Truth(r[0], r[1], tuple(r[2]), r[3], r[4]) for r in rows]


def save_detections(
    connection: duckdb.DuckDBPyConnection, detections: list[Detection]
) -> None:
    initialize_schema(connection)
    connection.execute("DELETE FROM detections")
    if detections:
        connection.executemany(
            "INSERT OR REPLACE INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (d.detection_id, d.layer.value, d.detector, d.event_type, list(d.meter_ids),
                 d.start, d.end, d.seen_at, d.severity, d.score, d.message)
                for d in detections
            ],
        )


def run_detection(
    connection: duckdb.DuckDBPyConnection, settings: FactorySettings, use_ml: bool = True
) -> tuple[list[Detection], list[Score]]:
    data = load_plant_data(
        connection, settings.demand.contract_capacity_kw, settings.demand.interval_minutes
    )
    detections = detect_all(data, use_ml)
    save_detections(connection, detections)
    return detections, evaluate(detections, load_truths(connection))
