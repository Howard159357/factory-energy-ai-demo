from base64 import b64decode
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from factory_energy.anomaly.service import run_detection
from factory_energy.config.loader import load_meters, load_settings
from factory_energy.dashboard.app import create_app
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.data import DashboardData
from factory_energy.dashboard.pages import (
    anomalies,
    demand,
    equipment,
    forecast,
    history,
    overview,
    plantmap,
)
from factory_energy.dashboard.playbook import shed_options
from factory_energy.dashboard.status import Level, projection
from factory_energy.dashboard.widgets import equipment_status
from factory_energy.energy.tariff import (
    energy_cost,
    exceedance_penalty,
    money,
    period,
    power_factor_adjustment,
)
from factory_energy.simulator.generator import SimulationConfig, run_simulation
from factory_energy.simulator.scenarios import load_scenarios

INCIDENT = datetime(2025, 6, 16, 8, 10)
QUIET = datetime(2025, 6, 11, 3, 0)


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("dash") / "plant.duckdb"
    s2 = next(s for s in load_scenarios() if s.id == "S2")
    with duckdb.connect(str(path)) as connection:
        config = SimulationConfig(date(2025, 6, 9), 9, 42, (s2,))
        run_simulation(connection, config, load_settings(), load_meters())
        run_detection(connection, load_settings(), use_ml=False)
    return path


@pytest.fixture(scope="module")
def ctx(database: Path) -> Iterator[Context]:
    yield Context(DashboardData(database), load_settings(), load_meters())


def test_clock_ticks_jumps_and_stops_at_the_end() -> None:
    start = datetime(2025, 6, 16, 6)
    clock = ClockState(start, start, start + timedelta(minutes=12), speed="300x")
    assert clock.tick().now == start + timedelta(minutes=5)
    assert ClockState.from_store(clock.to_store()) == clock
    end = clock.tick().tick().tick()
    assert end.now == clock.end and not end.playing
    assert clock.jump(start - timedelta(days=1)).now == start
    assert clock.toggled().tick() == clock.toggled()
    assert clock.jump(clock.end).restarted().now == start


def test_tariff_and_projection() -> None:
    tariff = load_settings().tariff
    stamps = pd.DatetimeIndex([
        "2025-06-16 08:30", "2025-06-16 09:00", "2025-06-16 16:00", "2025-06-16 22:00",
        "2025-06-21 10:00", "2025-06-22 10:00", "2025-11-03 10:00", "2025-11-03 12:00",
        "2025-05-15 16:00", "2025-10-15 16:00",
    ])  # summer Mon x4, Sat, Sun, November Mon x2, the day before summer, its last day
    assert period(stamps, tariff).tolist() == [
        "off_peak", "half_peak", "peak", "half_peak", "saturday", "off_peak",
        "half_peak", "off_peak", "half_peak", "peak",
    ]
    summer = tariff.energy_per_kwh.summer
    cost = energy_cost(pd.Series([60.0, 60.0], index=stamps[:2]), tariff)
    assert cost == pytest.approx(summer["off_peak"] + summer["half_peak"])
    regular = tariff.demand_per_kw_month.summer["regular"]
    peak_time = datetime(2025, 6, 16, 16, 0)
    assert exceedance_penalty(1300, 1250, tariff, peak_time) == pytest.approx(50 * 2 * regular)
    assert exceedance_penalty(1400, 1250, tariff, peak_time) == pytest.approx(
        (125 * 2 + 25 * 3) * regular)  # x2 up to 10% of the contract, x3 beyond
    off_peak = tariff.demand_per_kw_month.summer["off_peak"]
    assert exceedance_penalty(1300, 1250, tariff, datetime(2025, 6, 16, 8, 15)) == pytest.approx(
        50 * 2 * off_peak)
    assert exceedance_penalty(1200, 1250, tariff, peak_time) == 0
    assert power_factor_adjustment(0.70, tariff) == pytest.approx(0.010)  # 10 points below 80%
    assert power_factor_adjustment(0.84, tariff) == pytest.approx(-0.004)
    assert power_factor_adjustment(0.99, tariff) == pytest.approx(-0.015)  # capped at 95%
    assert money(6400, tariff) == "NT$6,400 (US$200)"
    series = pd.DataFrame({"kw": [100.0, 100.0, 160.0]})
    assert projection(series) == (3, 120.0, (360 + 160 * 12) / 15)
    assert equipment_status(50, 100) == "RUNNING"
    assert equipment_status(5, 100) == "IDLE"
    assert equipment_status(1, 100) == "OFF"


def test_tick_state_during_the_incident(ctx: Context) -> None:
    state = ctx.tick(INCIDENT)
    assert state is ctx.tick(INCIDENT)  # shared by every callback of the same tick
    assert state.projected_kw > ctx.contract_kw and state.level is Level.ALARM
    assert "above" in state.headline and "Shed" in state.action
    quiet = ctx.tick(QUIET)
    assert quiet.level is Level.OK and quiet.cost_today > 0
    options = shed_options(ctx, state.snapshot)
    # playbook order (SOP-03 step 2), not largest first: EV charging is paused first
    assert [o.action for o in options][:2] == ["Pause EV charging",
                                               "Delay the next burn-in loading"]
    assert options[0].shed_kw < options[1].shed_kw
    assert state.action.index("Pause EV charging") < state.action.index("burn-in")
    assert ctx.data.seed == 42 and ctx.whatif("S2") is not None


def test_pages_render_during_the_incident(ctx: Context) -> None:
    kpis, load, alerts, feeders = overview.update(ctx, INCIDENT)
    assert len(kpis) == 6 and load.data and feeders.data
    assert any("Simultaneous" in str(a) for a in alerts)
    clock = ClockState(INCIDENT, INCIDENT, INCIDENT, scenario="S2")
    dm_kpis, dm_fig, playbook, risk, sld = demand.update(ctx, clock)
    assert sld.startswith("data:image/svg+xml;base64,")
    assert "MDB-3" in b64decode(sld.split(",", 1)[1]).decode("utf-8")
    assert len(dm_kpis) == 4 and dm_fig.data and "Need to shed" in str(playbook)
    hero = demand.whatif_panel(ctx, "S2")
    assert hero is not None and "avoided" in str(hero)
    cards = equipment.cards(ctx, INCIDENT)
    assert len(cards) == 6 and "ALERT" in str(cards[0])
    rows = ctx.data.detections(INCIDENT)
    figure = anomalies.evidence(ctx, rows, None, INCIDENT)
    assert len(rows) >= 1 and figure.data
    assert max(max(trace.x) for trace in figure.data if len(trace.x)) <= INCIDENT
    assert forecast.day_figure(ctx, INCIDENT, "lightgbm") is not None  # renders w/o forecasts
    assert "No forecasts" in str(forecast.metrics_panel(ctx))
    assert history.heatmap(ctx).data and history.ranking(ctx, INCIDENT).data
    assert "Where the energy goes" in history.insight(ctx)
    bar, zones, _, map_alerts = plantmap.update(ctx, INCIDENT)
    assert len(zones) == 6 + 23 and "bad" in str(zones) and "kW" in str(bar) and map_alerts
    later = plantmap.update(ctx, datetime(2025, 6, 16, 8, 50))  # plant-level detection is open
    zone_items = [z for z in later[1] if "zone" in z.className]
    dots = [z for z in later[1] if z.className == "eq"]
    assert len(zone_items) == 6 and "bad" in str(zone_items)
    assert len(dots) == len(ctx.data.equipment_ids) and "eq-chip" in str(dots)


def test_detections_only_appear_once_detectable(ctx: Context) -> None:
    before = ctx.data.detections(datetime(2025, 6, 16, 8, 2))
    after = ctx.data.detections(datetime(2025, 6, 16, 8, 30))
    assert "SIMULTANEOUS_START" not in set(before.event_type)
    assert "SIMULTANEOUS_START" in set(after.event_type)
    assert list(after.detected_ts) == sorted(after.detected_ts, reverse=True)


def test_replay_window_and_highlight(ctx: Context) -> None:
    start, end = ctx.replay_window("S2")
    assert start == datetime(2025, 6, 16, 6) and end == datetime(2025, 6, 16, 11)
    assert ctx.data.highlight("S2", start, end) == datetime(2025, 6, 16, 8)
    fallback_start, fallback_end = ctx.replay_window("S99")
    assert ctx.data.first_ts <= fallback_start < fallback_end <= ctx.data.last_ts
    assert ctx.default_scenario() == "S2"


def test_app_builds_with_all_pages(database: Path) -> None:
    app = create_app(database, load_settings(), load_meters())
    assert len(app.callback_map) >= 12
    assert "SYNTHETIC DEMO DATA" in str(app.layout)
    assert "chat-fab" in str(app.layout) and "chat-input" in str(app.layout)  # on every page
