from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from factory_energy.dashboard.context import Context
from factory_energy.dashboard.data import DashboardData
from factory_energy.dashboard.playbook import shed_options
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext

REGISTRY = build_registry()
S2_MORNING = {"start": "2025-06-16T06:00", "end": "2025-06-16T11:00"}


def call(ctx: ToolContext, name: str, **arguments: object) -> dict:
    result = REGISTRY.call(ctx, name, arguments)
    assert result.ok, result.error
    return result.content


def test_registry_declares_schemas_and_permissions() -> None:
    permissions = REGISTRY.permissions()
    assert len(permissions) == 12
    assert [n for n, p in permissions.items() if p == "write"] == ["generate_report"]
    read_only = {t.name for t in REGISTRY.available(allow_write=False)}
    assert "generate_report" not in read_only and len(read_only) == 11
    schema = REGISTRY.tools["get_demand"].openai_schema()["function"]["parameters"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"start", "end"}


def test_demand_reproduces_the_simultaneous_start(ctx: ToolContext) -> None:
    demand = call(ctx, "get_demand", **S2_MORNING)
    assert demand["peak_kw"] == pytest.approx(1324.4, abs=0.2)
    assert demand["peak_interval_start"] == "2025-06-16T08:15"
    assert demand["intervals_over_contract"] == 2 and len(demand["series"]) == 20
    longer = call(ctx, "get_demand", start="2025-06-10", end="2025-06-17")
    assert "daily" in longer and "series" not in longer
    assert "interval_in_progress" not in demand and "interval_in_progress" not in longer


def test_demand_projects_the_interval_in_progress_like_the_alarm(ctx: ToolContext) -> None:
    # Monday 08:20: 08:00-08:15 is complete, 08:15-08:30 has run 5 minutes. The dashboard
    # alarm at that moment reads "Projected demand 1,329 kW is 79 kW above the contract".
    demand = call(ctx, "get_demand", start="2025-06-16T08:00", end="2025-06-16T08:20")
    assert demand["series"][0]["kw"] == pytest.approx(1307.1, abs=0.1)
    running = demand["interval_in_progress"]
    assert running["start"] == "2025-06-16T08:15" and running["minutes_elapsed"] == 5
    assert running["projected_kw"] == pytest.approx(1329.1, abs=0.1)
    assert running["projected_minus_contract_kw"] == pytest.approx(79.1, abs=0.1)
    only = call(ctx, "get_demand", start="2025-06-16T08:15", end="2025-06-16T08:20")
    assert only["intervals"] == 0 and only["interval_in_progress"] == running


def test_equipment_status_in_one_call(ctx: ToolContext) -> None:
    status = call(ctx, "get_equipment_status", as_of="2025-06-16T08:30")
    assert status["as_of"] == "2025-06-16T08:30" and len(status["equipment"]) == 23
    assert sum(status["counts"].values()) == 23
    ovens = {e["id"]: e for e in status["equipment"] if e["id"].startswith("RF-")}
    assert all(o["state"] == "RUNNING" and o["kw"] > 0.2 * o["rated_kw"] for o in ovens.values())
    night = call(ctx, "get_equipment_status", as_of="2025-06-15T03:00")  # Sunday night
    assert night["counts"]["RUNNING"] < status["counts"]["RUNNING"]
    latest = call(ctx, "get_equipment_status")  # no moment: just after the last reading
    assert latest["as_of"] > call(ctx, "get_plant_overview")["data_to"]


def test_present_load_is_the_one_the_dashboard_playbook_sheds(ctx: ToolContext) -> None:
    # Monday 08:20, the agent clip's moment: EV charging stepped up at 08:15, so its 15-minute
    # mean understates the present load that the playbook (and SOP-03) sheds.
    moment = datetime(2025, 6, 16, 8, 20)
    status = call(replace(ctx, as_of=moment), "get_equipment_status")
    ev = next(e for e in status["equipment"] if e["id"] == "EV-01")
    dashboard = Context(DashboardData(ctx.db_path), ctx.settings, ctx.catalog)
    options = shed_options(dashboard, dashboard.tick(moment).snapshot)
    assert options[0].action == "Pause EV charging"  # playbook order, not largest first
    assert ev["kw_now"] == pytest.approx(options[0].load_kw, abs=0.05)
    assert ev["kw"] < ev["kw_now"] and "kw_now" in status["fields"]


def test_feeder_energy_adds_up_to_the_plant(ctx: ToolContext) -> None:
    window = {"start": "2025-06-10", "end": "2025-06-12"}
    plant = call(ctx, "get_energy", by="plant", **window)
    feeders = call(ctx, "get_energy", by="feeder", **window)
    assert feeders["total_kwh"] == pytest.approx(plant["total_kwh"], rel=1e-4)
    assert sum(i["share"] for i in feeders["items"]) == pytest.approx(1.0, abs=0.01)
    assert set(plant["kwh_by_tou_period"]) <= {"peak", "half-peak", "off-peak",
                                              "Saturday half-peak"}


def test_series_and_stats_of_one_meter(ctx: ToolContext) -> None:
    series = call(ctx, "get_meter_series", meter_id="ch-02", metric="kw", **S2_MORNING)
    assert series["meter_id"] == "CH-02" and series["series"]["bucket_minutes"] == 5
    assert len(series["series"]["mean"]) == len(series["series"]["max"]) == 60
    assert series["series"]["first_bucket_start"] == "2025-06-16T06:00"
    summary = series["window_summary"]
    assert summary["minutes"] == 300 and summary["min"] <= summary["mean"] <= summary["max"]
    stats = call(ctx, "compute_stats", meter_id="IM-04", **S2_MORNING)
    assert stats["rated_kw"] == 90 and stats["max_kw"] > 0.9 * 90 * 0.9
    plant = call(ctx, "compute_stats", meter_id="PLANT", **S2_MORNING)
    assert plant["mean_power_factor"] is None and plant["energy_kwh"] > 0


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("get_demand", {"start": "2025-01-01", "end": "2025-03-01"}, "at most 31 days"),
        ("get_demand", {"start": "2025-06-16", "end": "2025-06-15"}, "end must be after"),
        ("get_demand", {**S2_MORNING, "sql": "DROP TABLE x"}, "Extra inputs"),
        ("compute_stats", {"meter_id": "ZZ-99", **S2_MORNING}, "unknown meter"),
        ("get_meter_series", {"meter_id": "PLANT", "metric": "pf", **S2_MORNING}, "only kw"),
        ("get_demand", {"start": "2024-01-01", "end": "2024-01-02"}, "no readings"),
        ("no_such_tool", {}, "unknown tool"),
    ],
)
def test_bad_calls_are_refused_with_a_reason(
    ctx: ToolContext, name: str, arguments: dict, message: str
) -> None:
    result = REGISTRY.call(ctx, name, arguments)
    assert not result.ok and message in result.error


def test_detections_stored_and_on_demand(ctx: ToolContext) -> None:
    stored = call(ctx, "list_detections", start="2025-06-16", end="2025-06-17")
    kinds = {d["event_type"] for d in stored["detections"]}
    assert {"SIMULTANEOUS_START", "DEMAND_EXCEEDANCE"} <= kinds
    exceedance = next(d for d in stored["detections"] if d["event_type"] == "DEMAND_EXCEEDANCE")
    assert "kW over" in exceedance["impact"] and "NT$" in exceedance["impact"]
    fresh = call(ctx, "detect_anomalies", start="2025-06-16", end="2025-06-17")
    assert any(d["event_type"] == "SIMULTANEOUS_START" for d in fresh["detections"])


def test_forecast_never_shows_the_future(ctx: ToolContext) -> None:
    early = call(ctx, "get_forecast", as_of="2025-06-16T07:59", horizon_minutes=60)
    assert early["issued_at"] == "2025-06-16T07:30"  # 07:45 has not closed yet
    assert early["next_hour_alert_level"] == "OK"
    later = call(ctx, "get_forecast", as_of="2025-06-16T08:20", horizon_minutes=120)
    assert later["issued_at"] == "2025-06-16T07:45" and later["next_hour_alert_level"] == "ALARM"
    riskiest = max((f for f in later["forecasts"] if f["horizon_min"] <= 60),
                   key=lambda f: f["p_exceed"])  # the interval the dashboard's maximum is for
    assert later["next_hour_max_interval_start"] == riskiest["interval_start"]
    last = later["forecasts"][-1]
    assert last["interval_start"] == "2025-06-16T09:45"
    assert last["interval_end"] == "2025-06-16T10:00"
    actuals = {f["horizon_min"]: f["actual_kw"] for f in later["forecasts"]}
    assert actuals[15] is not None and actuals[30] is None and actuals[120] is None
    assert not REGISTRY.call(ctx, "get_forecast", {"as_of": "2025-01-05T00:00"}).ok


def test_whatif_staggered_start_removes_the_exceedance(ctx: ToolContext) -> None:
    whatif = call(ctx, "whatif_staggered_start", scenario_id="S2", stagger_minutes=15)
    assert whatif["actual_peak_kw"] > 1250 > whatif["staggered_peak_kw"]
    assert whatif["reduction_kw"] > 150 and whatif["exceedance_penalty_avoided"].startswith("NT$")
    assert not REGISTRY.call(ctx, "whatif_staggered_start", {"scenario_id": "S3"}).ok


def test_report_tool_writes_only_when_allowed(ctx: ToolContext, tmp_path: Path) -> None:
    arguments = {"title": "../../etc/Weekly summary", "body_markdown": "Peak was 1,324 kW.",
                 "citations": ["docs/knowledge/sop/SOP-01_monday_startup.md#Purpose"]}
    refused = REGISTRY.call(ctx, "generate_report", arguments)
    assert not refused.ok and "disabled" in refused.error
    assert not (tmp_path / "reports").exists()
    writer = replace(ctx, allow_write=True)
    written = call(writer, "generate_report", **arguments)
    files = list((tmp_path / "reports").glob("*.md"))
    assert [f.name for f in files] == [written["path"]] and ".." not in written["path"]
    assert "synthetic data" in files[0].read_text(encoding="utf-8")


def test_knowledge_search_returns_citations(ctx: ToolContext) -> None:
    result = call(ctx, "search_knowledge", query="weekend shutdown checklist reflow oven", k=3)
    assert result["passages"][0]["citation"].startswith("docs/knowledge/")


def test_a_missing_database_is_an_error_not_a_crash(ctx: ToolContext, tmp_path: Path) -> None:
    missing = replace(ctx, db_path=tmp_path / "absent.duckdb")
    result = REGISTRY.call(missing, "get_demand", S2_MORNING)
    assert not result.ok and "build-demo" in result.error
