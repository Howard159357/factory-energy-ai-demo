from __future__ import annotations

import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.int64]

MINUTES_PER_DAY = 1440
# Random processes that span days (weather persistence, burn-in batches) start here.
EPOCH = date(2020, 1, 1)


@dataclass(frozen=True)
class Timeline:
    """A run of whole days at one-minute resolution, in plant local time."""

    start: date
    days: int
    minute_of_day: IntArray = field(init=False, repr=False)
    day_index: IntArray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.days <= 0:
            raise ValueError("days must be positive")
        object.__setattr__(self, "minute_of_day", np.tile(np.arange(MINUTES_PER_DAY), self.days))
        object.__setattr__(self, "day_index", np.repeat(np.arange(self.days), MINUTES_PER_DAY))

    @property
    def minutes(self) -> int:
        return self.days * MINUTES_PER_DAY

    @property
    def dates(self) -> list[date]:
        return [self.start + timedelta(days=offset) for offset in range(self.days)]

    @property
    def hour(self) -> FloatArray:
        return self.minute_of_day / 60.0

    def timestamps(self) -> npt.NDArray[np.datetime64]:
        origin = np.datetime64(self.start.isoformat(), "m")
        return origin + np.arange(self.minutes).astype("timedelta64[m]")

    def per_day(self, values: npt.ArrayLike) -> FloatArray:
        """Broadcast one value per day to every minute of that day."""
        return np.repeat(np.asarray(values, dtype=np.float64), MINUTES_PER_DAY)

    def mask(self, intervals: list[tuple[int, int]]) -> BoolArray:
        """Boolean minute mask from absolute [start, end) minute intervals (clipped)."""
        result = np.zeros(self.minutes, dtype=np.bool_)
        for start, end in intervals:
            lo, hi = max(start, 0), min(end, self.minutes)
            if lo < hi:
                result[lo:hi] = True
        return result


def rng_for(seed: int, *keys: str) -> np.random.Generator:
    """Independent, reproducible random stream for (seed, key...)."""
    entropy = [seed, *(zlib.crc32(key.encode("utf-8")) for key in keys)]
    return np.random.default_rng(np.random.SeedSequence(entropy))


def minutes_since_on(on: BoolArray) -> IntArray:
    """Minutes elapsed since the latest OFF->ON transition (large where off)."""
    index = np.arange(on.size)
    starts = np.where(on & ~np.concatenate(([False], on[:-1])), index, -1)
    last_start = np.maximum.accumulate(starts)
    since = index - last_start
    return np.where(on & (last_start >= 0), since, np.iinfo(np.int64).max // 2)


def extend(on: BoolArray, before: int = 0, after: int = 0) -> BoolArray:
    """Turn equipment on `before` minutes early and keep it on `after` minutes late."""
    counts = np.concatenate(([0], np.cumsum(on, dtype=np.int64)))
    index = np.arange(on.size)
    lo = np.clip(index - after, 0, on.size)
    hi = np.clip(index + before + 1, 0, on.size)
    return np.asarray((counts[hi] - counts[lo]) > 0, dtype=np.bool_)


def delay_starts(on: BoolArray, delay_for: Callable[[int], int]) -> BoolArray:
    """Postpone each ON block's start by delay_for(start_minute) minutes."""
    result = on.copy()
    for start in np.flatnonzero(on & ~np.concatenate(([False], on[:-1]))):
        result[start:start + delay_for(int(start))] = False
    return result


@dataclass(frozen=True)
class RandomSource:
    """Random draws keyed by calendar day, so a given day is identical in any simulation window.

    Without this, a one-day run and a one-year run would produce different values for the same
    day, which would break scenario replay and tests.
    """

    seed: int
    timeline: Timeline
    keys: tuple[str, ...]

    def day(self, day: date, *tags: str) -> np.random.Generator:
        return rng_for(self.seed, *self.keys, day.isoformat(), *tags)

    def day_of(self, minute: int, *tags: str) -> np.random.Generator:
        return self.day(self.timeline.start + timedelta(days=minute // MINUTES_PER_DAY), *tags)

    def stream(self, *tags: str) -> np.random.Generator:
        """A stream that does not depend on dates (constants such as phase offsets)."""
        return rng_for(self.seed, *self.keys, *tags)

    def noise(self, relative: float, smooth: int = 5, tag: str = "noise") -> FloatArray:
        parts = [
            noise(self.day(day, tag), MINUTES_PER_DAY, relative, smooth)
            for day in self.timeline.dates
        ]
        return np.concatenate(parts)


def noise(rng: np.random.Generator, size: int, relative: float, smooth: int = 5) -> FloatArray:
    """Multiplicative noise around 1.0 with a little temporal correlation."""
    raw = rng.normal(0.0, relative, size + smooth - 1)
    kernel = np.ones(smooth) / np.sqrt(smooth)
    return np.asarray(1.0 + np.convolve(raw, kernel, mode="valid"), dtype=np.float64)
