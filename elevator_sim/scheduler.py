"""Elevator assignment strategies.

DestinationDispatchScheduler (the main algorithm)
-------------------------------------------------
When a passenger submits (source, dest) we ask each elevator one question:

    "If I gave you this passenger, how much extra total passenger-time would
     the system incur?"

We answer it by *simulating* the elevator forward (a "what-if" run) twice:
once without the new passenger, once with. The difference in the sum of
everyone's (dropoff_time - request_time) is the cost. The elevator with the
lowest cost gets the passenger.

Because the what-if uses the real elevator rules, the cost automatically
accounts for direction, capacity, detours, and delay imposed on people who
are already assigned. It only uses passengers already submitted - no peeking.

NearestElevatorScheduler is a naive baseline for comparison.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import List, Optional

from .elevator import Elevator
from .models import Passenger


class Scheduler(ABC):
    @abstractmethod
    def choose(self, passenger: Passenger, elevators: List[Elevator], now: int) -> Elevator:
        """Pick the elevator for this passenger."""


def projected_total_time(elevator: Elevator, now: int, extra: Optional[Passenger] = None) -> int:
    """Sum of total times of everyone assigned to `elevator` (plus `extra`),
    assuming no further requests arrive. Pure function: does not touch the real elevator."""
    sim = elevator.clone()
    if extra is not None:
        sim.waiting.append(replace(extra))
    tracked = sim.riders + sim.waiting
    t, guard = now, 100_000
    while sim.riders or sim.waiting:
        sim.serve_floor(t)
        sim.plan_direction()
        sim.move()
        t += 1
        guard -= 1
        if guard == 0:
            raise RuntimeError("projection did not terminate - scheduling bug")
    return sum(p.dropoff_time - p.request_time for p in tracked)


class DestinationDispatchScheduler(Scheduler):
    def choose(self, passenger: Passenger, elevators: List[Elevator], now: int) -> Elevator:
        def cost(e: Elevator):
            added = projected_total_time(e, now, passenger) - projected_total_time(e, now)
            # tie-breakers: spread load, then lowest id (deterministic)
            return (added, e.assigned_count, e.id)
        return min(elevators, key=cost)


class NearestElevatorScheduler(Scheduler):
    """Baseline: closest car wins. Ignores direction, load and who else is waiting."""

    def choose(self, passenger: Passenger, elevators: List[Elevator], now: int) -> Elevator:
        return min(elevators, key=lambda e: (abs(e.floor - passenger.source), e.assigned_count, e.id))


SCHEDULERS = {
    "dispatch": DestinationDispatchScheduler,
    "nearest": NearestElevatorScheduler,
}
