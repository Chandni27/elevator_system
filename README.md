# Destination-Dispatch Elevator Simulation

Pure Python 3.8+, no dependencies.

```bash
python3 main.py --requests sample_requests.csv --compare   # run sample, writes elevator_positions.csv
python3 main.py --random 200 --seed 7 --elevators 4 --floors 30 --capacity 6 --compare
python3 -m unittest discover -s tests -v                   # 16 tests
```

```python
from elevator_sim import Request, simulate, build_report
reqs = [Request(10, "passenger3", 20, 1), (0, "passenger1", 1, 12)]   # Request, tuple, or dict all work
result = simulate(reqs, num_elevators=3, num_floors=20, capacity=4, log_path="positions.csv")
print(build_report(result))
```

CLI flags: `--elevators`, `--floors`, `--capacity`, `--scheduler {dispatch,nearest}`, `--log FILE`,
`--random N --seed S --pattern {uniform,rush}`, `--compare`.

---

## Requirements checklist

| # | Requirement | Status | Where / how it is verified |
|---|---|---|---|
| 1a | Serve every request eventually | **Met** for any finite input | Assigned passengers are never dropped; a full car always has dropoffs to make; `max_time` guard raises on deadlock. `test_req1_everyone_served...` |
| 1a | No passenger waits indefinitely | **Partly met** - see "Starvation" below | No hard wait bound; empirical waits are about 1-2 sweeps at normal load |
| 1b | Minimize total time (wait + ride) | **Met** (heuristic, not provably optimal) | Dispatcher minimizes the added total passenger-time; beats nearest-car baseline in `--compare` |
| 1c | Capacity honored | **Met** | `Elevator.serve_floor`; `test_req1_capacity_never_exceeded_from_log` recomputes load from the log |
| 1c | Direction logic honored | **Met** | Cars only pick up passengers going their way; `test_req1_direction_logic_from_log` |
| 2 | Origin + destination at request time; assignment final | **Met** | `Simulation._admit` sets `elevator_id` once; nothing reassigns or edits a destination. `test_req2_assignment_is_final_and_honored` |
| 3 | 1 time unit = 1 floor, discrete ticks, no wall clock | **Met** | Tick loop in `Simulation.run`; idle gaps still tick (`test_idle_gap_is_ticked_through`) |
| 4 | Configurable elevators, floors, capacity | **Met** | `Config`, `simulate(...)`, CLI flags. `test_req4_configurable_sizes` |
| 5 | Scheduler; input `time,id,source,dest`; no peeking | **Met** | `RequestFeed.poll(now)` only releases requests with `time <= now`. `test_req5_no_peeking` proves removing future requests changes nothing before they arrive |
| 6 | Position log: one row per timestamp from 0 | **Met** | `elevator_positions.csv`: header `time,elevator_0,...`, then one row per tick |
| 7 | Min/max/avg wait and total + observations | **Met** | `stats.build_report`: min/max/avg/median/p90/stdev, histogram, overhead vs ideal, per-car utilisation |

### Starvation (the one honest gap)
For a finite input every passenger is served, and the simulation proves it by finishing. But there is no *hard* upper bound on one passenger's wait. A car sweeps the whole building in at most `floors - 1` ticks, so a waiting passenger is normally reached within a sweep or two. The one way to be skipped repeatedly is a car that is full every time it reaches their floor. Measured max waits (5 seeds each):

| Load | Avg wait | Max wait | Floors |
|---|---|---|---|
| Light (60 req / 400 t, 3 cars) | 4.7 | 22 | 20 |
| Medium (200 req / 400 t) | 6.8 | 33 | 20 |
| Heavy (300 req / 200 t, 4 cars, cap 6) | 17.9 | 111 | 30 |
| Overload (400 req / 100 t, 3 cars) | 85.3 | 323 | 20 |

Under overload long waits are a queue (demand exceeds capacity), not a bug. A hard guarantee needs an aging rule (see "What I'd improve").

---

## Layout

| File | Responsibility |
|---|---|
| `elevator_sim/models.py` | `Request` (input row) and `Passenger` (timestamps, wait/ride/total) |
| `elevator_sim/elevator.py` | One car: capacity, direction logic, unload/load/move per tick |
| `elevator_sim/scheduler.py` | Assignment: `DestinationDispatchScheduler` + nearest-car baseline |
| `elevator_sim/simulation.py` | `RequestFeed` (no peeking), tick loop, position log |
| `elevator_sim/stats.py` | Statistics and observations report |
| `main.py` | CLI, CSV loader, random request generator, scheduler comparison |
| `tests/` | `test_simulation.py` (behavior), `test_requirements.py` (requirement checks from the output) |

## Time model
* Integer time `t`. One tick = one floor of travel. Boarding/unloading is instant.
* Every tick: (1) requests with `time == t` arrive and are assigned; (2) each car unloads then loads; (3) each car picks a direction; (4) **positions are logged for `t`**; (5) each car moves one floor.
* The loop ticks every integer from 0 to the end, even if the input jumps ahead.
* `wait = pickup - request`, `ride = dropoff - pickup`, `total = dropoff - request`.

## Algorithm

### Movement: LOOK (a one-direction sweep)
* Keep going while anything is ahead (a rider's destination or an assigned pickup).
* Reverse only when nothing is ahead; idle if nothing at all.
* Only pick up passengers heading the way the car is travelling. An empty car with nothing ahead follows the longest-waiting passenger on its floor.
* Never exceed capacity. A full car ignores pickups until someone gets off; left-behind passengers stay assigned and are picked up on a later pass.

### Assignment: "what-if" cost
For a new request, ask every car: *how much extra total passenger-time would you add?*
1. Clone the car, run it to empty with the real rules -> sum of everyone's total time (`base`).
2. Same with the new passenger added (`with`).
3. `cost = with - base`. Lowest cost wins; ties go to the car with fewer assigned passengers, then lowest id.

The projection reuses the real elevator code, so direction, capacity, detours and delay to people already assigned are all priced in, and the prediction cannot drift from reality.

### Sample result (300 rush-hour requests, 4 cars, 30 floors, capacity 6)
| Scheduler | Avg wait | Avg total | Max total |
|---|---|---|---|
| dispatch (what-if cost) | 62.9 | 75.3 | 287 |
| nearest car (baseline) | 104.1 | 116.4 | 473 |

## Why LOOK (and not something else)
* **It is the direction logic.** The spec requires direction rules; a sweep makes "go one way, pick up people going that way" the whole policy, with no special cases.
* **Predictable and explainable.** A sweep takes at most `floors - 1` ticks, so you can reason about worst cases and starvation. Customers and interviewers can follow it.
* **Cheap to simulate.** The dispatcher runs the movement rule many times per request (every car, twice). A simple rule keeps that fast.
* **Versus FCFS:** serving in arrival order zig-zags the building and wastes travel.
* **Versus nearest-first (SSTF):** cheap but can starve far-away floors and ignores direction.
* **Versus route insertion / optimization:** these can beat LOOK on average but are heavier to build, test and explain. They are the natural next step once there is data showing LOOK is the bottleneck.

## Assumptions
* Floors are numbered `1..N`; all cars start at floor 1 at `t = 0`.
* Passengers are at their source floor exactly at their request time (no walking time) and always board when a car arrives going their way with room.
* Capacity is a passenger count, not weight.
* Every car serves every floor.
* Requests with the same `time` are assigned in input order; each sees the earlier ones.
* The position logged for time `t` is the car's floor after loading and before it moves.
* Invalid input is rejected with `ValueError`: floor out of range, `source == dest`, negative time, duplicate id.
* Optimization target is **average total time** (sum of wait + ride), not worst case.

## Simplifications
* No door open/close time, acceleration, or different speeds. Boarding is instant.
* No breakdowns, closed floors, or cancelled/changed requests (the spec says assignment is final).
* No group arrivals, VIP/freight modes, or energy cost.
* Batch input: a fixed request list is replayed, not a live stream (`RequestFeed` is the seam where a stream would plug in).
* The `max_time` guard (default 1,000,000 ticks) is a safety net, not a feature.

## What I'd improve with more time
1. **Express and designated elevators.** Give each car a set of floors it serves (`Elevator.serves_floors`). Examples: an express car that only stops at the lobby and floors 20-40, "low-rise" and "high-rise" banks. The dispatcher would only consider eligible cars. Trips between banks need a transfer at a sky lobby, which breaks "one elevator per passenger", so that is a product decision.
2. **Hard starvation guarantee.** Add an aging term (e.g. cost grows with `wait^2`) or reserve capacity for passengers waiting beyond a threshold.
3. **Route insertion.** Keep an ordered stop list per car and insert each pickup/dropoff at the cheapest legal position, replacing the strict sweep.
4. **Tail-aware objective.** Minimize p95 or sum of squares, not just the mean.
5. **Pre-positioning.** Idle cars drift to the lobby at morning peak or to the busiest floors.
6. **Realism.** Door time, acceleration, weight limits, failures with reassignment of waiting passengers.
7. **Scale.** Zoning, cap the projection horizon, cache base projections, evaluate only the best few candidate cars.
8. **Evaluation.** Replay real building traffic, compare against an offline lower bound, run A/B across schedulers.

## Known limitations
* Greedy, one request at a time; not globally optimal.
* Mean-focused: tail waits can be long under heavy load.
* Starvation guarantee is empirical (see above), not formal.

---

# Interview prep

## Likely follow-up questions (and short answers)
1. **Why not just send the nearest car?** It ignores direction, load and who is on board. In the rush-hour test, its average total time was about 55% higher.
2. **Time complexity?** Per request: E cars x O(S) projection steps (S = ticks until the car empties). Total O(R x E x S). Cache the base projection per car per tick to halve it.
3. **Is it optimal?** No: greedy/online dial-a-ride. Measure the gap against an offline lower bound.
4. **Can anyone starve?** Not for finite input; no hard bound under sustained overload. Fix with aging.
5. **Full car passing a waiting passenger?** Pickups aren't targets while full; the passenger stays assigned and is picked up on a later sweep; the cost function priced that delay in.
6. **Car breaks or floor closes?** Mark it out of service and reassign its waiting passengers (riders are stuck). That relaxes "assignment is final".
7. **Scale to 100 floors / 20 cars?** Zoning, capped projections, cached baselines, evaluate top-k cars.
8. **How do you validate it?** Invariant tests derived from the output (capacity, direction, one floor per tick, everyone served, no peeking), randomized configs, baseline comparison, replay real traffic.
9. **Why a `Scheduler` interface?** Swap and A/B algorithms on identical input.
10. **Which metric?** Average, p95 or max wait is a business decision; ask who the building serves.

## FDE priorities
1. Clarify the real objective first (average vs worst-case wait, energy, accessibility).
2. Safety and correctness invariants over cleverness; encode them as tests.
3. Ship a simple explainable baseline, then iterate with before/after numbers.
4. Observability: logs, percentiles, utilisation, so you can explain a long wait.
5. Test on realistic bursty traffic, not just uniform random.
6. Configuration without code changes.
7. Failure modes and fallbacks (bad input, deadlock guard, dispatcher crash).
8. Explain trade-offs to non-engineers ("cuts average wait ~40% but a few people wait longer; here's the knob").
9. Integrate with the customer's systems and monitor in production.
