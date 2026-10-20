from datetime import datetime, timedelta

from factory_energy.analytics.bi_utils import (
    auto_granularity,
    parse_click_meter,
    percent_change,
    previous_period,
    weekday_hour_profile,
)

START = datetime(2026, 3, 2)


def test_previous_period_and_granularity() -> None:
    assert previous_period(START, START + timedelta(days=7)) == (START - timedelta(days=7), START)
    assert auto_granularity(START, START + timedelta(days=1)) == "minute"
    assert auto_granularity(START, START + timedelta(days=8)) == "hour"
    assert auto_granularity(START, START + timedelta(days=365)) == "day"


def test_percent_change_and_click_safety() -> None:
    assert percent_change(110, 100) == 10
    assert percent_change(110, 0) is None
    assert parse_click_meter({"points": [{"customdata": "IM-01"}]}, {"IM-01"}) == "IM-01"
    assert parse_click_meter({"points": [{"customdata": "EVIL"}]}, {"IM-01"}) is None
    assert parse_click_meter(None, {"IM-01"}) is None


def test_weekday_hour_profile() -> None:
    rows = [(START, 10.0), (START.replace(minute=30), 20.0), (START + timedelta(days=1), 99.0)]
    profile = weekday_hour_profile(rows)
    assert profile[0] == {"weekday": 0, "hour": 0, "average_kw": 15.0, "samples": 2}
