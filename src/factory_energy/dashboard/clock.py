"""The replay clock: simulated time that advances a fixed number of minutes per tick."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

SPEEDS: dict[str, int] = {  # label -> simulated minutes per one-second tick
    "60x": 1,
    "300x": 5,
    "900x": 15,
    "3600x": 60,
}
DEFAULT_SPEED = "300x"
ISO = "%Y-%m-%dT%H:%M"


@dataclass(frozen=True)
class ClockState:
    now: datetime
    start: datetime
    end: datetime
    speed: str = DEFAULT_SPEED
    playing: bool = True
    scenario: str | None = None

    def to_store(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("now", "start", "end"):
            data[key] = data[key].strftime(ISO)
        return data

    @classmethod
    def from_store(cls, data: dict[str, Any]) -> ClockState:
        scenario = data.get("scenario")
        return cls(
            now=datetime.strptime(data["now"], ISO),
            start=datetime.strptime(data["start"], ISO),
            end=datetime.strptime(data["end"], ISO),
            speed=str(data.get("speed", DEFAULT_SPEED)),
            playing=bool(data.get("playing", True)),
            scenario=None if scenario is None else str(scenario),
        )

    def tick(self) -> ClockState:
        """Advance one tick; stop at the end of the replay window."""
        if not self.playing:
            return self
        step = timedelta(minutes=SPEEDS.get(self.speed, SPEEDS[DEFAULT_SPEED]))
        now = min(self.now + step, self.end)
        return ClockState(now, self.start, self.end, self.speed, now < self.end, self.scenario)

    def jump(self, when: datetime) -> ClockState:
        now = min(max(when, self.start), self.end)
        return ClockState(now, self.start, self.end, self.speed, self.playing, self.scenario)

    def with_speed(self, speed: str) -> ClockState:
        return ClockState(self.now, self.start, self.end, speed, self.playing, self.scenario)

    def toggled(self) -> ClockState:
        return ClockState(self.now, self.start, self.end, self.speed, not self.playing,
                          self.scenario)

    def restarted(self) -> ClockState:
        return ClockState(self.start, self.start, self.end, self.speed, True, self.scenario)
