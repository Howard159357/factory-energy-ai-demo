"""What a tool can reach: a read-only plant database, the configuration and the knowledge base."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from factory_energy.config.loader import load_meters, load_settings
from factory_energy.config.models import FactorySettings, MeterCatalog
from factory_energy.rag.settings import REPO_ROOT
from factory_energy.rag.store import KnowledgeStore
from factory_energy.storage.connection import open_local

MAX_WINDOW = timedelta(days=31)


@cache
def _plant_zone() -> ZoneInfo:
    return ZoneInfo(load_settings().plant.timezone)


def to_plant_time(value: datetime) -> datetime:
    """Readings are stored in plant local time without a zone: convert aware inputs to it."""
    if value.tzinfo is None:
        return value
    return value.astimezone(_plant_zone()).replace(tzinfo=None)


PlantTime = Annotated[datetime, AfterValidator(to_plant_time)]


class Arguments(BaseModel):
    """Base of every tool input: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class Window(Arguments):
    start: PlantTime
    end: PlantTime

    @model_validator(mode="after")
    def bounded(self) -> Window:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.end - self.start > MAX_WINDOW:
            raise ValueError("the window may span at most 31 days")
        return self


@dataclass
class ToolContext:
    db_path: Path
    settings: FactorySettings
    catalog: MeterCatalog
    knowledge: Callable[[], KnowledgeStore] | None = None
    allow_write: bool = False
    quarantine: bool = True  # strip instruction-like text from retrieved passages
    # The replay clock's "now": when set, no tool may return data from after this moment.
    as_of: datetime | None = None
    report_dir: Path = REPO_ROOT / "reports" / "agent"
    _connection: duckdb.DuckDBPyConnection | None = field(default=None, init=False, repr=False)
    _store: KnowledgeStore | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        knowledge: Callable[[], KnowledgeStore] | None = None,
    ) -> ToolContext:
        values = os.environ if env is None else env
        path = Path(values.get("FACTORY_ENERGY_DB", "data/plant.duckdb"))
        return cls(
            db_path=path if path.is_absolute() else REPO_ROOT / path,
            settings=load_settings(),
            catalog=load_meters(),
            knowledge=knowledge,
            allow_write=values.get("AGENT_ALLOW_WRITE", "0") == "1",
            quarantine=values.get("AGENT_QUARANTINE", "1") != "0",
        )

    @property
    def contract_kw(self) -> float:
        return self.settings.demand.contract_capacity_kw

    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            if not self.db_path.exists():
                raise FileNotFoundError(f"{self.db_path} not found; run `build-demo` first")
            self._connection = open_local(self.db_path, read_only=True)
        return self._connection

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
        with self._lock:
            return self.connection().execute(sql, params).df()

    def store(self) -> KnowledgeStore:
        if self._store is None:
            if self.knowledge is None:
                raise RuntimeError("no knowledge base configured")
            self._store = self.knowledge()
        return self._store

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def apply_cutoff(ctx: ToolContext, args: BaseModel) -> BaseModel:
    """Clip a tool's time arguments to ``ctx.as_of`` so nothing after "now" can be read."""
    if ctx.as_of is None:
        return args
    update: dict[str, datetime] = {}
    fields = type(args).model_fields
    if "start" in fields and "end" in fields:
        start, end = args.start, args.end  # type: ignore[attr-defined]
        if start >= ctx.as_of:
            raise LookupError(f"the window starts after the current time "
                              f"{ctx.as_of:%Y-%m-%d %H:%M}; that data does not exist yet")
        update["end"] = min(end, ctx.as_of)
    if "as_of" in fields:
        given = args.as_of  # type: ignore[attr-defined]
        update["as_of"] = ctx.as_of if given is None else min(given, ctx.as_of)
    return args.model_copy(update=update) if update else args


def iso(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return None
    return str(pd.Timestamp(value).isoformat(timespec="minutes"))


def num(value: Any, digits: int = 1) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)
