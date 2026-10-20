from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime


def validate_kwh(values: Iterable[float | None]) -> list[str]:
    """Flag problems in a cumulative kWh register without changing the values."""
    warnings: list[str] = []
    previous: float | None = None
    for value in values:
        if value is None:
            warnings.append("KWH_NULL")
            continue
        if previous is not None and value < previous:
            warnings.append("KWH_DECREASE")
            if value < previous * 0.5:
                warnings.append("KWH_RESET_SUSPECTED")
        previous = value
    return warnings


def align_minute(timestamp: datetime) -> datetime:
    return timestamp.replace(second=0, microsecond=0)
