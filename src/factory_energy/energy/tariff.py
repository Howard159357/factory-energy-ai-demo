"""Money view of energy and demand, using the time-of-use tariff in config/factory.yaml.

The tariff follows Taipower's high-voltage three-segment structure: summer and other seasons,
peak / half-peak / Saturday / off-peak periods, a demand charge per contract type, exceedance
billed at 2x the period's contract rate up to 10% over the contract and 3x beyond, and a
power-factor adjustment around 80%.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from factory_energy.config.models import SeasonHours, TariffSettings

# The contract whose unit price applies to demand in each period.
CONTRACT_OF = {"peak": "regular", "half_peak": "half_peak", "saturday": "saturday",
               "off_peak": "off_peak"}
PERIOD_NAMES = {"peak": "peak", "half_peak": "half-peak", "saturday": "Saturday half-peak",
                "off_peak": "off-peak"}


def is_summer(ts: pd.DatetimeIndex, tariff: TariffSettings) -> np.ndarray:
    day = ts.month * 100 + ts.day
    start = int(tariff.summer_start.replace("-", ""))
    end = int(tariff.summer_end.replace("-", ""))
    return np.asarray((day >= start) & (day <= end))


def _in_hours(hour: np.ndarray, ranges: tuple[tuple[int, int], ...]) -> np.ndarray:
    inside = np.zeros(hour.shape, dtype=bool)
    for start, end in ranges:
        inside |= (hour >= start) & (hour < end)
    return inside


def period(ts: pd.DatetimeIndex, tariff: TariffSettings) -> pd.Series:
    """Time-of-use period of each timestamp: peak, half_peak, saturday or off_peak."""
    hour = np.asarray(ts.hour)
    weekday = np.asarray(ts.weekday)
    summer = is_summer(ts, tariff)
    out = np.full(len(ts), "off_peak", dtype=object)
    groups: tuple[tuple[np.ndarray, SeasonHours], ...] = (
        (summer & (weekday < 5), tariff.hours.summer_weekday),
        (~summer & (weekday < 5), tariff.hours.other_weekday),
        (summer & (weekday == 5), tariff.hours.summer_saturday),
        (~summer & (weekday == 5), tariff.hours.other_saturday),
    )
    for mask, hours in groups:
        for name in ("half_peak", "saturday", "peak"):  # peak last: it wins any overlap
            out[mask & _in_hours(hour, getattr(hours, name))] = name
    return pd.Series(out, index=ts)


def _season(summer: bool) -> str:
    return "summer" if summer else "other"


def energy_rates(ts: pd.DatetimeIndex, tariff: TariffSettings) -> np.ndarray:
    periods = period(ts, tariff).to_numpy()
    summer = is_summer(ts, tariff)
    return np.array([getattr(tariff.energy_per_kwh, _season(s))[p]
                     for s, p in zip(summer, periods, strict=True)], dtype=float)


def energy_cost(minute_kw: pd.Series, tariff: TariffSettings) -> float:
    """Cost of a 1-minute kW series (index = timestamps)."""
    if minute_kw.empty:
        return 0.0
    rates = energy_rates(pd.DatetimeIndex(minute_kw.index), tariff)
    return float((minute_kw.to_numpy() / 60.0 * rates).sum())


def rate_at(ts: datetime, tariff: TariffSettings) -> float:
    return float(energy_rates(pd.DatetimeIndex([ts]), tariff)[0])


def average_rate(tariff: TariffSettings, year: int = 2025) -> float:
    """Mean energy price over every hour of a year: the cost of a load that never stops."""
    hours = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", inclusive="left")
    return float(energy_rates(hours, tariff).mean())


def period_at(ts: datetime, tariff: TariffSettings) -> str:
    return str(period(pd.DatetimeIndex([ts]), tariff).iloc[0])


def exceedance_penalty(
    peak_kw: float, contract_kw: float, tariff: TariffSettings, when: datetime
) -> float:
    """Extra demand charge for one month when demand in `when`'s period exceeds the contract.

    The excess is billed at the period's contract price: 2x up to 10% of the contract, 3x
    beyond. Only the regular contract is held, so every period is judged against it.
    """
    excess = max(peak_kw - contract_kw, 0.0)
    if excess == 0:
        return 0.0
    rule = tariff.exceedance
    within = min(excess, contract_kw * rule.band)
    beyond = excess - within
    summer = bool(is_summer(pd.DatetimeIndex([when]), tariff)[0])
    prices: dict[str, float] = getattr(tariff.demand_per_kw_month, _season(summer))
    price = prices[CONTRACT_OF[period_at(when, tariff)]]
    return float((within * rule.within + beyond * rule.beyond) * price)


def power_factor_adjustment(power_factor: float, tariff: TariffSettings) -> float:
    """Change of the monthly bill as a share: positive is a surcharge, negative a credit."""
    rule = tariff.power_factor
    points = (min(power_factor, rule.cap) - rule.base) * 100
    return float(-round(points) * rule.step)


def money(value: float, tariff: TariffSettings) -> str:
    """NT$ with the US$ equivalent, e.g. "NT$6,652 (US$208)"."""
    return f"{tariff.currency}{value:,.0f} (US${value / tariff.ntd_per_usd:,.0f})"
