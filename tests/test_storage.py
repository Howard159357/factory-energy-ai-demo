from datetime import datetime, timedelta

import duckdb
import pytest

from factory_energy.config.loader import load_meters
from factory_energy.storage.connection import open_local
from factory_energy.storage.models import MinuteReading
from factory_energy.storage.repository import LocalRepository
from factory_energy.storage.schema import initialize_schema
from factory_energy.storage.validation import align_minute, validate_kwh

START = datetime(2026, 3, 2, 8, 0)


def repo() -> LocalRepository:
    connection = open_local()
    initialize_schema(connection)
    return LocalRepository(connection)


def scalar(repository: LocalRepository, sql: str) -> object:
    row = repository.connection.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_meter_master_from_catalog() -> None:
    repository = repo()
    repository.load_meter_master(load_meters())
    count = "SELECT COUNT(*) FROM meter_master WHERE "
    assert scalar(repository, count + "include_in_plant_total") == 6
    assert scalar(repository, count + "meter_type = 'EQUIPMENT'") == 23


def test_equipment_cannot_join_plant_total() -> None:
    repository = repo()
    with pytest.raises(duckdb.ConstraintException):
        repository.connection.execute(
            "INSERT INTO meter_master VALUES ('X-01','x','EQUIPMENT','MDB-1','c',1,true,true)"
        )


def test_idempotent_upsert_and_series() -> None:
    repository = repo()
    readings = [MinuteReading("MDB-1", START + timedelta(minutes=i), kw=float(i)) for i in range(3)]
    repository.insert_minute_batch(readings + readings[:1])
    assert scalar(repository, "SELECT COUNT(*) FROM meter_reading_minute") == 3
    assert repository.latest_timestamp("MDB-1") == START + timedelta(minutes=2)
    assert len(repository.meter_series(["MDB-1"], START, START + timedelta(minutes=3))) == 3
    with pytest.raises(ValueError):
        repository.meter_series(["MDB-1"], START, START, metric="kw; DROP TABLE x")


def test_validation_and_path_guard() -> None:
    assert validate_kwh([1, None, 0.2]) == ["KWH_NULL", "KWH_DECREASE", "KWH_RESET_SUSPECTED"]
    assert align_minute(datetime(2026, 3, 2, 8, 0, 42)).second == 0
    with pytest.raises(ValueError):
        open_local("Server=db.example.invalid;Driver=x")
