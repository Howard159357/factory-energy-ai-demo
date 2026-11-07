"""Shared fixtures for the tool, agent and MCP tests: a small simulated plant database."""

import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from factory_energy.anomaly.service import run_detection
from factory_energy.config.loader import load_meters, load_settings
from factory_energy.rag.embed import HashEmbedder
from factory_energy.rag.ingest import DEFAULT_SOURCES, discover, ingest
from factory_energy.rag.store import KnowledgeStore, persistent_client
from factory_energy.simulator.generator import SimulationConfig, run_simulation
from factory_energy.simulator.scenarios import load_scenarios
from factory_energy.tools.context import ToolContext

FORECAST_ISSUE = datetime(2025, 6, 16, 7, 45)


@pytest.fixture(scope="session")
def plant_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Nine days around the S2 simultaneous start, with detections and a few forecasts."""
    path = tmp_path_factory.mktemp("plant") / "plant.duckdb"
    s2 = next(s for s in load_scenarios() if s.id == "S2")
    with duckdb.connect(str(path)) as connection:
        run_simulation(connection, SimulationConfig(date(2025, 6, 9), 9, 42, (s2,)),
                       load_settings(), load_meters())
        run_detection(connection, load_settings(), use_ml=False)
        rows = []
        for issue, p_exceed in ((FORECAST_ISSUE - timedelta(minutes=15), 0.1),
                                (FORECAST_ISSUE, 0.6)):
            for horizon in (15, 30, 60, 120):
                target = issue + timedelta(minutes=horizon)
                rows.append((issue, target, horizon, 1180.0, 1240.0, 1300.0, p_exceed,
                             1250.0 + horizon, "lightgbm"))
        connection.executemany("INSERT INTO forecasts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return path


@pytest.fixture(scope="session")
def chroma(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """One on-disk Chroma for the whole session. In-memory clients share process-wide state
    that a garbage-collected client can tear down, which made tests flaky."""
    return persistent_client(tmp_path_factory.mktemp("chroma"))


@pytest.fixture(scope="session")
def knowledge(chroma: Any) -> KnowledgeStore:
    store = KnowledgeStore(chroma, HashEmbedder(), f"agent-{uuid.uuid4().hex}")
    ingest(store, discover(DEFAULT_SOURCES))
    return store


@pytest.fixture
def ctx(plant_db: Path, knowledge: KnowledgeStore, tmp_path: Path) -> Iterator[ToolContext]:
    context = ToolContext(plant_db, load_settings(), load_meters(), lambda: knowledge,
                          report_dir=tmp_path / "reports")
    yield context
    context.close()
