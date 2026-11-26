"""The tick loop that ties elevators, scheduler and input together."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .elevator import Elevator
from .models import Passenger, Request
from .scheduler import DestinationDispatchScheduler, Scheduler


@dataclass
class Config:
    num_elevators: int = 3
    num_floors: int = 20
    capacity: int = 4
    start_floor: int = 1

    def validate(self) -> None:
        if self.num_elevators < 1 or self.num_floors < 2 or self.capacity < 1:
            raise ValueError("need >=1 elevator, >=2 floors, capacity >=1")
        if not 1 <= self.start_floor <= self.num_floors:
            raise ValueError("start_floor out of range")


class RequestFeed:
    """Hands out requests only when their time has arrived.

    The scheduler never sees the underlying list, so it cannot peek ahead.
    """

    def __init__(self, requests: Sequence[Request]):
        self._pending = sorted(requests, key=lambda r: r.time)
        self._next = 0

    def poll(self, now: int) -> List[Request]:
        out = []
        while self._next < len(self._pending) and self._pending[self._next].time <= now:
            out.append(self._pending[self._next])
            self._next += 1
        return out

    @property
    def has_more(self) -> bool:
        return self._next < len(self._pending)


@dataclass
class SimulationResult:
    config: Config
    passengers: List[Passenger]
    elevators: List[Elevator]
    position_log: List[List[int]] = field(default_factory=list)  # [time, pos_e0, pos_e1, ...]
    end_time: int = 0

    def write_position_log(self, path: str) -> None:
        with open(path, "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["time"] + [f"elevator_{e.id}" for e in self.elevators])
            w.writerows(self.position_log)


class Simulation:
    def __init__(self, config: Config, scheduler: Optional[Scheduler] = None):
        config.validate()
        self.config = config
        self.scheduler = scheduler or DestinationDispatchScheduler()

    def _admit(self, req: Request, elevators: List[Elevator], seen: Dict[str, Passenger]) -> Passenger:
        c = self.config
        if req.id in seen:
            raise ValueError(f"duplicate passenger id: {req.id}")
        if req.time < 0:
            raise ValueError(f"{req.id}: negative request time")
        if not (1 <= req.source <= c.num_floors and 1 <= req.dest <= c.num_floors):
            raise ValueError(f"{req.id}: floor out of range 1..{c.num_floors}")
        if req.source == req.dest:
            raise ValueError(f"{req.id}: source and dest are the same floor")
        p = Passenger(req.id, req.time, req.source, req.dest)
        chosen = self.scheduler.choose(p, elevators, req.time)   # decision is final
        p.elevator_id = chosen.id
        chosen.waiting.append(p)
        seen[p.id] = p
        return p

    def run(self, requests: Sequence[Request], log_path: Optional[str] = None,
            max_time: int = 1_000_000) -> SimulationResult:
        c = self.config
        elevators = [Elevator(i, c.capacity, c.start_floor) for i in range(c.num_elevators)]
        feed = RequestFeed(requests)
        passengers: Dict[str, Passenger] = {}
        log: List[List[int]] = []

        t = 0
        while True:
            # 1) new requests arrive and are assigned immediately
            for req in feed.poll(t):
                self._admit(req, elevators, passengers)
            # 2) every car unloads / loads at its current floor
            for e in elevators:
                e.serve_floor(t)
            # 3) every car decides where to go next
            for e in elevators:
                e.plan_direction()
            # 4) log where everyone is at time t
            log.append([t] + [e.floor for e in elevators])
            # 5) stop when nothing is left to do
            if not feed.has_more and all(p.dropoff_time is not None for p in passengers.values()):
                break
            # 6) advance one time unit (one floor of travel)
            for e in elevators:
                e.move()
            t += 1
            if t > max_time:
                raise RuntimeError("simulation exceeded max_time - possible deadlock")

        result = SimulationResult(c, list(passengers.values()), elevators, log, t)
        if log_path:
            result.write_position_log(log_path)
        return result


def simulate(requests: Sequence[Request], num_elevators: int = 3, num_floors: int = 20,
             capacity: int = 4, log_path: Optional[str] = None,
             scheduler: Optional[Scheduler] = None) -> SimulationResult:
    """Convenience entry point: list of requests in, finished simulation out."""
    sim = Simulation(Config(num_elevators, num_floors, capacity), scheduler)
    return sim.run(requests, log_path)
