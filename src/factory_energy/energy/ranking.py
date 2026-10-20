from __future__ import annotations

from factory_energy.energy.models import RankingItem


def rank_meters(
    values: dict[str, float], unit: str, plant_total: float | None = None
) -> list[RankingItem]:
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=True)
    return [
        RankingItem(rank, meter, value, unit, value / plant_total if plant_total else None)
        for rank, (meter, value) in enumerate(ordered, 1)
    ]
