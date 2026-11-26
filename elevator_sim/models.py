"""Plain data objects used across the simulation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Request:
    """One line of input: a passenger shows up at `time` and says where they are going."""
    time: int
    id: str
    source: int
    dest: int


@dataclass
class Passenger:
    """A request that has been accepted. Timestamps are filled in as the sim runs."""
    id: str
    request_time: int
    source: int
    dest: int
    elevator_id: Optional[int] = None   # set once, at request time, never changed
    pickup_time: Optional[int] = None   # when they stepped into the elevator
    dropoff_time: Optional[int] = None  # when they stepped out

    @property
    def direction(self) -> int:
        """+1 if going up, -1 if going down."""
        return 1 if self.dest > self.source else -1

    @property
    def wait_time(self) -> int:
        return self.pickup_time - self.request_time

    @property
    def ride_time(self) -> int:
        return self.dropoff_time - self.pickup_time

    @property
    def total_time(self) -> int:
        return self.dropoff_time - self.request_time

    @property
    def ideal_time(self) -> int:
        """Best case: elevator is already here and goes non-stop."""
        return abs(self.dest - self.source)
