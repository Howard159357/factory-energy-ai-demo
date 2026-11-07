"""Golden answers computed directly from the simulated data, independently of the agent's tools.

Each value is a small SQL or numpy computation on the raw minute readings (or, for the what-if,
a re-run of the simulator itself), so the agent cannot be graded by its own code path. The
database fingerprint (seed, window, simulator version) is stored with the values and checked
before a run, so answers are never compared against a different dataset.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from factory_energy.config.models import FactorySettings, MeterCatalog
from factory_energy.energy.tariff import energy_rates
from factory_energy.evaluation.questions import EVAL_DIR
from factory_energy.simulator.scenarios import AirLeak, load_scenarios
from factory_energy.simulator.whatif import staggered_start

GOLDEN = EVAL_DIR / "golden.json"
PLANT_MINUTES = """
    SELECT r.ts, SUM(r.kw) AS kw FROM meter_reading_minute r JOIN meter_master m USING (meter_id)
    WHERE m.include_in_plant_total AND r.ts >= ? AND r.ts < ? GROUP BY r.ts ORDER BY r.ts
"""


@dataclass(frozen=True)
class Source:
    connection: duckdb.DuckDBPyConnection
    settings: FactorySettings
    catalog: MeterCatalog

    def scalar(self, sql: str, *params: Any) -> float:
        row = self.connection.execute(sql, params).fetchone()
        if row is None or row[0] is None:
            raise LookupError(f"no data for golden query: {sql[:60]}")
        return float(row[0])

    def plant(self, start: str, end: str) -> pd.Series:
        frame = self.connection.execute(PLANT_MINUTES, (start, end)).df()
        if frame.empty:
            raise LookupError(f"no plant data between {start} and {end}")
        return frame.set_index("ts").kw

    def demand(self, start: str, end: str) -> pd.Series:
        """Fixed 15-minute means, complete intervals only."""
        kw = self.plant(start, end)
        groups = kw.groupby(kw.index.floor("15min"))
        return groups.mean()[groups.size() == 15]

    def meter_kwh(self, meter: str, start: str, end: str) -> float:
        return self.scalar("SELECT SUM(kw) / 60 FROM meter_reading_minute "
                           "WHERE meter_id = ? AND ts >= ? AND ts < ?", meter, start, end)


def _s2_peak(src: Source) -> float:
    return float(src.demand("2025-06-16", "2025-06-17").max())


def _s3_over(src: Source) -> float:
    demand = src.demand("2025-07-23", "2025-07-25")
    return float((demand > src.settings.demand.contract_capacity_kw).sum())


def _plant_kwh_jul(src: Source) -> float:
    return float(src.plant("2025-07-01", "2025-07-08").sum() / 60)


def _top_feeder_june(src: Source) -> float:
    return max(src.meter_kwh(f, "2025-06-01", "2025-07-01") for f in src.catalog.feeder_ids)


def _rf02_weekend(src: Source) -> float:
    return src.meter_kwh("RF-02", "2025-10-17 12:00", "2025-10-20 12:00")


def _mdb3_pf(src: Source) -> float:
    return src.scalar("SELECT AVG(pf) FROM meter_reading_minute WHERE meter_id = 'MDB-3' "
                      "AND ts >= '2025-11-05 08:00' AND ts < '2025-11-05 17:00'")


def _night_base(src: Source) -> float:
    kw = src.plant("2025-08-06 02:00", "2025-08-06 05:00")
    return float(kw.median())


def _s2_staggered(src: Source) -> float:
    s2 = next(s for s in load_scenarios() if s.id == "S2")
    seed = int(src.scalar("SELECT seed FROM simulation_runs LIMIT 1"))
    result = staggered_start(s2, src.settings, src.catalog, seed, 15)
    assert result is not None
    return result.staggered_peak_kw


def _energy_cost(src: Source) -> float:
    kw = src.plant("2025-08-04", "2025-08-11")
    rates = energy_rates(pd.DatetimeIndex(kw.index), src.settings.tariff)
    return float((kw.to_numpy() / 60 * rates).sum())


def _forecast_pct(src: Source) -> float:
    issued = src.connection.execute(
        "SELECT MAX(issue_ts) FROM forecasts WHERE model = 'lightgbm' "
        "AND issue_ts <= TIMESTAMP '2025-07-23 13:20' - INTERVAL 15 MINUTE").fetchone()
    if issued is None or issued[0] is None:
        raise LookupError("no forecast")
    return 100 * src.scalar("SELECT MAX(p_exceed) FROM forecasts WHERE model = 'lightgbm' "
                            "AND issue_ts = ? AND horizon_min <= 60", issued[0])


def _air_leak(src: Source) -> float:
    leak = next(e for s in load_scenarios() for e in s.events if isinstance(e, AirLeak))
    return leak.max_kw


def _mdb4_season(src: Source) -> float:
    return (src.meter_kwh("MDB-4", "2025-07-01", "2025-08-01")
            - src.meter_kwh("MDB-4", "2025-01-01", "2025-02-01"))


def _mdb5_after_leak(src: Source) -> float:  # X01: the 7 days from the leak detection day
    return src.meter_kwh("MDB-5", "2025-09-09", "2025-09-16")


def _mdb5_before_leak(src: Source) -> float:  # X01: the 7 days before it
    return src.meter_kwh("MDB-5", "2025-09-02", "2025-09-09")


def _mdb3_pf_nov3(src: Source) -> float:  # X02: the day the low power factor was first detected
    return src.scalar("SELECT AVG(pf) FROM meter_reading_minute WHERE meter_id = 'MDB-3' "
                      "AND ts >= '2025-11-03 08:00' AND ts < '2025-11-03 17:00'")


def _plant_kwh_q3(src: Source) -> float:  # X05: longer than one 31-day tool window
    return float(src.plant("2025-07-01", "2025-10-01").sum() / 60)


# name -> (computation, whether it is available on the small smoke database)
COMPUTATIONS: dict[str, tuple[Callable[[Source], float], bool]] = {
    "s2_peak_kw": (_s2_peak, True),
    "s3_intervals_over_contract": (_s3_over, True),
    "plant_kwh_jul_1_7": (_plant_kwh_jul, True),
    "top_feeder_kwh_june": (_top_feeder_june, False),
    "rf02_weekend_kwh": (_rf02_weekend, False),
    "mdb3_pf_nov5_day": (_mdb3_pf, False),
    "plant_night_base_aug6": (_night_base, False),
    "s2_staggered_peak_kw": (_s2_staggered, True),
    "plant_energy_cost_aug_week": (_energy_cost, False),
    "forecast_pexceed_jul23_1320_pct": (_forecast_pct, False),
    "air_leak_kw": (_air_leak, True),
    "mdb4_july_minus_january_kwh": (_mdb4_season, False),
    "mdb5_kwh_sep9_15": (_mdb5_after_leak, False),
    "mdb5_kwh_sep2_8": (_mdb5_before_leak, False),
    "mdb3_pf_nov3_day": (_mdb3_pf_nov3, False),
    "plant_kwh_q3": (_plant_kwh_q3, False),
}


def fingerprint(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    row = connection.execute("SELECT seed, simulator_version FROM simulation_runs LIMIT 1"
                             ).fetchone()
    if row is None:
        raise LookupError("database has no simulation_runs row")
    return {"seed": int(row[0]), "simulator_version": str(row[1])}


def compute(connection: duckdb.DuckDBPyConnection, settings: FactorySettings,
            catalog: MeterCatalog, only_smoke: bool = False,
            names: tuple[str, ...] = ()) -> dict[str, float]:
    src = Source(connection, settings, catalog)
    return {name: round(fn(src), 4) for name, (fn, smoke) in COMPUTATIONS.items()
            if (smoke or not only_smoke) and (not names or name in names)}


def save(values: dict[str, float], connection: duckdb.DuckDBPyConnection,
         path: Path = GOLDEN) -> None:
    payload = {"fingerprint": fingerprint(connection),
               "computed_at": datetime.now().isoformat(timespec="seconds"),
               "values": values}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load(connection: duckdb.DuckDBPyConnection, path: Path = GOLDEN) -> dict[str, float]:
    """Golden values, refusing a database generated with another seed or simulator version."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = fingerprint(connection)
    if payload["fingerprint"] != current:
        raise ValueError(f"golden answers were computed for {payload['fingerprint']}, "
                         f"the database is {current}; run `eval golden`")
    return {str(k): float(v) for k, v in payload["values"].items()}
