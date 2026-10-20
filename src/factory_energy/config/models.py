from __future__ import annotations

import datetime as dt
import re
from datetime import time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

METER_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")


class MeterType(StrEnum):
    FEEDER = "FEEDER"
    EQUIPMENT = "EQUIPMENT"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeederConfig(_Strict):
    meter_id: str
    name: str = Field(min_length=1)
    rated_kw: float = Field(gt=0)
    enabled: bool = True

    @field_validator("meter_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not METER_ID.fullmatch(value):
            raise ValueError("meter_id must be uppercase letters, digits and dashes")
        return value


class EquipmentConfig(FeederConfig):
    feeder: str
    category: str = Field(min_length=1)


class MeterCatalog(_Strict):
    feeders: tuple[FeederConfig, ...]
    equipment: tuple[EquipmentConfig, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> MeterCatalog:
        ids = [meter.meter_id for meter in (*self.feeders, *self.equipment)]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate meter_id")
        feeder_ids = {feeder.meter_id for feeder in self.feeders}
        unknown = sorted({item.feeder for item in self.equipment} - feeder_ids)
        if unknown:
            raise ValueError(f"equipment references unknown feeder(s): {', '.join(unknown)}")
        return self

    @property
    def feeder_ids(self) -> list[str]:
        """Meters that add up to the plant total."""
        return [feeder.meter_id for feeder in self.feeders if feeder.enabled]

    def equipment_on(self, feeder_id: str) -> list[EquipmentConfig]:
        return [item for item in self.equipment if item.feeder == feeder_id]


class PlantSettings(_Strict):
    name: str
    timezone: str
    description: str = ""


class DataSettings(_Strict):
    expected_interval_seconds: int = Field(gt=0)
    stale_after_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def stale_after_expected(self) -> DataSettings:
        if self.stale_after_seconds <= self.expected_interval_seconds:
            raise ValueError("stale_after_seconds must be greater than expected_interval_seconds")
        return self


class DemandSettings(_Strict):
    interval_minutes: int = Field(gt=0)
    contract_capacity_kw: float = Field(gt=0)
    warning_ratio: float = Field(default=0.9, gt=0, le=1)


class DashboardSettings(_Strict):
    refresh_seconds: int = Field(gt=0)


class TimeWindow(_Strict):
    start: time
    end: time


class Shift(TimeWindow):
    name: str


class ScheduleSettings(_Strict):
    shifts: tuple[Shift, ...]
    lunch_break: TimeWindow | None = None
    saturday: str = "half_plant"
    sunday: str = "maintenance_only"


PERIODS = ("peak", "half_peak", "saturday", "off_peak")
CONTRACTS = ("regular", "half_peak", "saturday", "off_peak")
HourRanges = tuple[tuple[int, int], ...]  # [start, end) in whole hours, end may be 24


class SeasonHours(_Strict):
    """Weekday or Saturday hours of each time-of-use period; the rest of the day is off-peak."""

    peak: HourRanges = ()
    half_peak: HourRanges = ()
    saturday: HourRanges = ()

    @field_validator("peak", "half_peak", "saturday")
    @classmethod
    def valid_hours(cls, value: HourRanges) -> HourRanges:
        for start, end in value:
            if not 0 <= start < end <= 24:
                raise ValueError(f"bad hour range {start}-{end}")
        return value


class TariffHours(_Strict):
    summer_weekday: SeasonHours
    other_weekday: SeasonHours
    summer_saturday: SeasonHours
    other_saturday: SeasonHours


class SeasonRates(_Strict):
    summer: dict[str, float]
    other: dict[str, float]


class ExceedanceRule(_Strict):
    band: float = Field(gt=0, lt=1)  # share of the contract billed at `within`
    within: float = Field(ge=1)
    beyond: float = Field(ge=1)


class PowerFactorRule(_Strict):
    base: float = Field(gt=0, lt=1)  # below it the bill rises, above it the bill falls
    step: float = Field(gt=0)  # share of the bill per percentage point
    cap: float = Field(gt=0, le=1)  # no further credit above this power factor


class TariffSettings(_Strict):
    """Time-of-use demand tariff used to express impact in money (see config/factory.yaml)."""

    name: str
    currency: str = "NT$"
    ntd_per_usd: float = Field(gt=0)  # illustrative exchange rate for the US$ figures
    summer_start: str = Field(pattern=r"^\d{2}-\d{2}$")  # MM-DD, inclusive
    summer_end: str = Field(pattern=r"^\d{2}-\d{2}$")
    hours: TariffHours
    energy_per_kwh: SeasonRates
    demand_per_kw_month: SeasonRates
    exceedance: ExceedanceRule
    power_factor: PowerFactorRule

    @model_validator(mode="after")
    def complete_rates(self) -> TariffSettings:
        for season in ("summer", "other"):
            energy = getattr(self.energy_per_kwh, season)
            demand = getattr(self.demand_per_kw_month, season)
            missing = [p for p in PERIODS if p not in energy and not (p == "peak" and
                                                                     season == "other")]
            missing += [c for c in CONTRACTS if c not in demand]
            if missing:
                raise ValueError(f"tariff {season} rates missing: {', '.join(missing)}")
        return self


class Holiday(_Strict):
    date: dt.date
    name: str


class FactorySettings(_Strict):
    plant: PlantSettings
    data: DataSettings
    demand: DemandSettings
    dashboard: DashboardSettings
    schedule: ScheduleSettings
    tariff: TariffSettings
    holidays: tuple[Holiday, ...] = ()

    def shift(self, name: str) -> Shift:
        for shift in self.schedule.shifts:
            if shift.name == name:
                return shift
        raise KeyError(f"shift not configured: {name}")
