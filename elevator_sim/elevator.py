"""One elevator car and the rules it follows on every tick.

Movement policy ("LOOK" / sweep):
  * Keep moving in the current direction while there is anything to do ahead.
  * Reverse only when nothing is left ahead.
  * Only pick up passengers who want to travel in the direction we are travelling.
  * Never board more than `capacity` riders.

The same methods are used by the real simulation AND by the scheduler's
"what-if" projections, so predictions match reality exactly.
"""
from __future__ import annotations

from dataclasses import replace
from typing import List, Set

from .models import Passenger

UP, DOWN, IDLE = 1, -1, 0


class Elevator:
    def __init__(self, elevator_id: int, capacity: int, start_floor: int = 1):
        self.id = elevator_id
        self.capacity = capacity
        self.floor = start_floor
        self.direction = IDLE
        self.riders: List[Passenger] = []    # inside the car
        self.waiting: List[Passenger] = []   # assigned to this car, still on their floor
        # statistics
        self.floors_travelled = 0
        self.max_load = 0
        self.delivered = 0

    # ------------------------------------------------------------------ helpers
    @property
    def is_full(self) -> bool:
        return len(self.riders) >= self.capacity

    @property
    def assigned_count(self) -> int:
        return len(self.riders) + len(self.waiting)

    def _targets(self) -> Set[int]:
        """Floors this car wants to visit. If full, pickups are pointless, so skip them."""
        floors = {p.dest for p in self.riders}
        if not self.is_full:
            floors |= {p.source for p in self.waiting}
        return floors

    def _has_target_ahead(self, targets: Set[int], direction: int) -> bool:
        return any((t - self.floor) * direction > 0 for t in targets)

    # ------------------------------------------------------------ per-tick steps
    def serve_floor(self, now: int) -> List[Passenger]:
        """Step 1 of a tick: let people off, then let people on. Takes zero time."""
        # 1) unload
        delivered = [p for p in self.riders if p.dest == self.floor]
        for p in delivered:
            p.dropoff_time = now
        self.riders = [p for p in self.riders if p.dest != self.floor]
        self.delivered += len(delivered)

        # 2) load (oldest request first)
        here = sorted((p for p in self.waiting if p.source == self.floor),
                      key=lambda p: p.request_time)
        if here and not self.is_full:
            # If the car is empty and has nothing ahead, it is "free" to pick any
            # direction -> follow the passenger who has waited longest.
            free = not self.riders and not self._has_target_ahead(self._targets(), self.direction)
            if free:
                self.direction = here[0].direction
            for p in here:
                if self.is_full:
                    break
                if p.direction == self.direction:   # direction rule
                    self.waiting.remove(p)
                    p.pickup_time = now
                    self.riders.append(p)
            self.max_load = max(self.max_load, len(self.riders))
        return delivered

    def plan_direction(self) -> None:
        """Step 2 of a tick: decide which way to go next (or idle)."""
        targets = self._targets()
        if not targets:
            self.direction = IDLE
            return
        if self.direction != IDLE:
            if self._has_target_ahead(targets, self.direction):
                return                                   # keep sweeping
            if self._has_target_ahead(targets, -self.direction):
                self.direction = -self.direction         # nothing ahead -> reverse
                return
        others = [t for t in targets if t != self.floor]
        if not others:
            self.direction = IDLE
            return
        nearest = min(others, key=lambda t: (abs(t - self.floor), t))
        self.direction = UP if nearest > self.floor else DOWN

    def move(self) -> None:
        """Step 3 of a tick: travel one floor (= one time unit)."""
        if self.direction != IDLE:
            self.floor += self.direction
            self.floors_travelled += 1

    # ------------------------------------------------------------------- what-if
    def clone(self) -> "Elevator":
        """Cheap copy for the scheduler's projections (passengers are copied too)."""
        c = Elevator(self.id, self.capacity, self.floor)
        c.direction = self.direction
        c.riders = [replace(p) for p in self.riders]
        c.waiting = [replace(p) for p in self.waiting]
        return c
