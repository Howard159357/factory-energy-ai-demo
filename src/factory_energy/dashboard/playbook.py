"""Load-shed playbook: what an operator can switch off or defer right now.

The shed shares are illustrative engineering assumptions for the demo plant, not measured
values; they are declared here in one place so the banner, the Demand page and the alerts
all agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from factory_energy.dashboard.context import Context


@dataclass(frozen=True)
class ShedRule:
    category: str  # equipment category in config/meters.yaml
    action: str
    share: float  # share of the present load that can be shed within minutes (assumption)


# In playbook order (EM-02 "Load-shed playbook", SOP-03 step 2): apply them top to bottom.
RULES: tuple[ShedRule, ...] = (
    ShedRule("ev_charger", "Pause EV charging", 1.0),
    ShedRule("burn_in", "Delay the next burn-in loading", 0.35),
    ShedRule("chiller", "Raise chilled-water setpoint +1 °C", 0.04),
    ShedRule("air_compressor_fixed", "Lower compressed-air pressure 0.5 bar", 0.035),
    ShedRule("air_compressor_vsd", "Lower compressed-air pressure 0.5 bar", 0.035),
)


@dataclass(frozen=True)
class ShedOption:
    action: str
    meters: tuple[str, ...]
    load_kw: float
    shed_kw: float


def shed_options(ctx: Context, snapshot: pd.DataFrame) -> list[ShedOption]:
    """Playbook rows for the present snapshot, merged by action, in playbook order (the order
    SOP-03 applies them), not by size."""
    meters = ctx.data.meters
    merged: dict[str, tuple[list[str], float, float]] = {}
    for rule in RULES:
        ids = [m for m in meters.index[meters.category == rule.category] if m in snapshot.index]
        load = float(snapshot.kw.reindex(ids).fillna(0.0).sum())
        names, total_load, total_shed = merged.get(rule.action, ([], 0.0, 0.0))
        merged[rule.action] = (names + ids, total_load + load, total_shed + load * rule.share)
    return [
        ShedOption(action, tuple(ids), load, shed) for action, (ids, load, shed) in merged.items()
    ]
