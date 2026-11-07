"""Money or energy impact of a detection, shared by the dashboard and the agent tools."""

from __future__ import annotations

from datetime import datetime

from factory_energy.config.models import TariffSettings
from factory_energy.energy.tariff import (
    PERIOD_NAMES,
    average_rate,
    exceedance_penalty,
    money,
    period_at,
    power_factor_adjustment,
    rate_at,
)


def impact_text(
    event_type: str, score: float, start: datetime, contract_kw: float, tariff: TariffSettings
) -> str:
    """One line of impact per detection, from its stored score."""
    if event_type == "DEMAND_EXCEEDANCE":
        penalty = exceedance_penalty(score, contract_kw, tariff, start)
        return (f"Impact: {score - contract_kw:,.0f} kW over in the "
                f"{PERIOD_NAMES[period_at(start, tariff)]} period · up to {money(penalty, tariff)}")
    if event_type == "OFF_SCHEDULE_RUNNING":
        cost = score * rate_at(start, tariff)
        return f"Impact: {score:,.0f} kWh wasted · about {money(cost, tariff)}"
    if event_type == "AIR_LEAK":
        yearly = score * 24 * 365 * average_rate(tariff)
        return f"Impact: +{score:,.0f} kW around the clock · about {money(yearly, tariff)}/year"
    if event_type == "SIMULTANEOUS_START":
        return f"Impact: {int(score)} machines started together"
    if event_type == "LOW_POWER_FACTOR":
        rule = tariff.power_factor
        change = power_factor_adjustment(score, tariff)
        best = -power_factor_adjustment(rule.cap, tariff)
        effect = (f"surcharge {change:.1%} of the bill" if change > 0
                  else f"bill credit {-change:.1%} instead of {best:.1%}")
        return (f"Impact: power factor {score:.2f} · {effect} "
                f"(surcharge below {rule.base:.2f})")
    return ""
