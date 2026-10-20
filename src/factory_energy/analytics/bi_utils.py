from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any


def previous_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    duration = end - start
    return start - duration, start


def auto_granularity(start: datetime, end: datetime) -> str:
    days = (end - start).total_seconds() / 86400
    if days <= 1:
        return "minute"
    if days <= 7:
        return "15min"
    return "hour" if days <= 90 else "day"


def percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100


def parse_click_meter(click_data: dict[str, Any] | None, allowed: set[str]) -> str | None:
    """Extract a meter_id from Plotly clickData, accepting only known meters."""
    if not isinstance(click_data, dict):
        return None
    try:
        meter = click_data["points"][0]["customdata"]
    except (KeyError, IndexError, TypeError):
        return None
    return meter if isinstance(meter, str) and meter in allowed else None


def weekday_hour_profile(rows: Iterable[tuple[datetime, float]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
    for timestamp, value in rows:
        grouped[(timestamp.weekday(), timestamp.hour)].append(float(value))
    return [
        {"weekday": wd, "hour": hour, "average_kw": sum(v) / len(v), "samples": len(v)}
        for (wd, hour), v in sorted(grouped.items())
    ]
