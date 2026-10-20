from __future__ import annotations

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS meter_master (
    meter_id VARCHAR PRIMARY KEY,
    display_name VARCHAR NOT NULL,
    meter_type VARCHAR NOT NULL CHECK (meter_type IN ('FEEDER', 'EQUIPMENT')),
    feeder_id VARCHAR,
    category VARCHAR,
    rated_kw DOUBLE NOT NULL,
    include_in_plant_total BOOLEAN NOT NULL,
    enabled BOOLEAN NOT NULL,
    CHECK (meter_type = 'FEEDER' OR include_in_plant_total = false),
    CHECK (meter_type = 'FEEDER' OR feeder_id IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS meter_reading_minute (
    meter_id VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    kwh DOUBLE,
    kw DOUBLE,
    pf DOUBLE,
    r_v DOUBLE,
    s_v DOUBLE,
    t_v DOUBLE,
    r_a DOUBLE,
    s_a DOUBLE,
    t_a DOUBLE,
    status INTEGER,
    PRIMARY KEY (meter_id, ts)
);
CREATE TABLE IF NOT EXISTS production_calendar (
    day DATE PRIMARY KEY,
    day_type VARCHAR NOT NULL,
    overtime BOOLEAN NOT NULL,
    holiday_name VARCHAR
);
CREATE TABLE IF NOT EXISTS weather_minute (
    ts TIMESTAMP PRIMARY KEY,
    temp_c DOUBLE NOT NULL
);
CREATE TABLE IF NOT EXISTS ground_truth_events (
    event_id VARCHAR PRIMARY KEY,
    scenario_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    meter_ids VARCHAR[] NOT NULL,
    start_ts TIMESTAMP NOT NULL,
    end_ts TIMESTAMP NOT NULL,
    severity VARCHAR NOT NULL,
    description VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL,
    caption VARCHAR NOT NULL DEFAULT '',
    description VARCHAR NOT NULL,
    replay_start TIMESTAMP NOT NULL,
    replay_end TIMESTAMP NOT NULL,
    what_if VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS detections (
    detection_id VARCHAR PRIMARY KEY,
    layer VARCHAR NOT NULL,
    detector VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    meter_ids VARCHAR[] NOT NULL,
    start_ts TIMESTAMP NOT NULL,
    end_ts TIMESTAMP NOT NULL,
    detected_ts TIMESTAMP NOT NULL,
    severity VARCHAR NOT NULL,
    score DOUBLE NOT NULL,
    message VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS forecasts (
    issue_ts TIMESTAMP NOT NULL,
    target_ts TIMESTAMP NOT NULL,
    horizon_min INTEGER NOT NULL,
    p10 DOUBLE NOT NULL,
    p50 DOUBLE NOT NULL,
    p90 DOUBLE NOT NULL,
    p_exceed DOUBLE NOT NULL,
    actual DOUBLE,
    model VARCHAR NOT NULL,
    PRIMARY KEY (model, target_ts, horizon_min)
);
CREATE TABLE IF NOT EXISTS forecast_runs (
    model VARCHAR NOT NULL,
    horizon_min INTEGER NOT NULL,
    origin_month VARCHAR NOT NULL,
    fingerprint VARCHAR NOT NULL,
    rows INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (model, horizon_min, origin_month)
);
CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id VARCHAR PRIMARY KEY,
    seed BIGINT NOT NULL,
    start_day DATE NOT NULL,
    days INTEGER NOT NULL,
    simulator_version VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL
);
"""


def initialize_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(SCHEMA)
