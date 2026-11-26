# Destination-Dispatch Elevator Simulation

Pure Python 3.8+, no dependencies.

```
python main.py --requests sample_requests.csv            # run the sample, writes elevator_positions.csv
python main.py --random 200 --seed 7 --elevators 4 --floors 30 --capacity 6 --compare
python -m unittest discover -s tests -v                  # 9 tests
```

```python
from elevator_sim import Request, simulate, build_report
reqs = [Request(10, "passenger3", 20, 1), ...]
result = simulate(reqs, num_elevators=3, num_floors=20, capacity=4, log_path="positions.csv")
print(build_report(result))
```

## Layout

| File | Responsibility |
|---|---|
| `elevator_sim/models.py` | `Request` (input row) and `Passenger` (timestamps, wait/ride/total) |
| `elevator_sim/elevator.py` | One car: capacity, direction logic, unload/load/move per tick |
| `elevator_sim/scheduler.py` | Assignment strategy: `DestinationDispatchScheduler` + naive baseline |
| `elevator_sim/simulation.py` | `RequestFeed` (no peeking), tick loop, position log |
| `elevator_sim/stats.py` | Min/max/avg/median/p90 + observations + elevator table |
| `main.py` | CLI, CSV loader, random request generator, scheduler comparison |

## Time model

* Time is an integer `t`. One tick = one floor of travel. Boarding/unloading is instant.
* Cars start at floor 1 at `t = 0`.
* Every tick, in this order:
  1. Requests with `time == t` arrive and are **assigned immediately** (final).
  2. Each car unloads, then loads, at its current floor.
  3. Each car picks its direction.
  4. **Positions are logged for `t`.**
  5. Each car moves one floor.
* The loop ticks every integer from 0 to the end, even if the input jumps from `t=3` to `t=100`.
* `wait = pickup - request`, `ride = dropoff - pickup`, `total = dropoff - request`.

### No peeking
The scheduler never sees the request list. `RequestFeed.poll(now)` only returns requests with `time <= now`. Test: `test_feed_does_not_peek`.

## Algorithm

### 1. Elevator rules (LOOK / sweep)
* Keep going in the current direction while anything is ahead (a rider's destination or an assigned pickup).
* Reverse only when nothing is ahead; idle if nothing at all.
* **Direction rule:** a car only picks up passengers heading the same way it is travelling. An empty car with nothing ahead is "free" and follows the longest-waiting passenger on its floor.
* **Capacity rule:** never exceed `capacity`. A full car ignores pickups (they are not targets) until someone gets off. Passengers left behind stay assigned and are picked up on a later pass.

### 2. Assignment ("what-if" cost)
For a new request, ask every car: *"how much extra total passenger-time would you add?"*
1. Clone the car, run it forward until it is empty (using the same rules, no future requests) -> sum of everyone's total time = `base`.
2. Same, but with the new passenger added -> `with`.
3. `cost = with - base`. The lowest cost wins; ties go to the car with fewer assigned passengers, then lowest id.

Why this works: direction, capacity, detours and delay imposed on people already assigned are all captured automatically, because the projection uses the same code as the real simulation. Minimizing the sum of total times is the same as minimizing average total time per passenger.

Cost: O(elevators x route length) per request. Fine for hundreds of floors, thousands of requests.

### 3. How each objective is met
| Objective | Mechanism |
|---|---|
| Serve everyone eventually | Assignments are never dropped; LOOK always reverses when nothing is ahead; a full car always has dropoffs to make, so it always makes progress; `max_time` guard raises on any deadlock bug |
| Minimize time per passenger | Cost = marginal increase in total passenger-time |
| Honor capacity + direction | Enforced in `Elevator.serve_floor`; tested |

### Sample result (300 rush-hour requests, 4 cars, 30 floors, capacity 6)
| scheduler | avg wait | avg total | max total |
|---|---|---|---|
| dispatch (what-if cost) | 62.9 | 75.3 | 287 |
| nearest car (baseline) | 104.1 | 116.4 | 473 |

(That load deliberately saturates the building; at normal load waits are far lower.)

## Known limitations (be upfront about these)
* **Greedy, one request at a time.** Doesn't re-optimize earlier assignments (not allowed anyway: assignments are final). Not globally optimal.
* **Weak starvation guarantee under sustained overload.** Every assigned passenger is eventually served for a finite input, but a person could wait a long time behind a stream of full cars. Fix: add an aging/fairness term to the cost (e.g. penalize `wait^2`).
* **Optimizes the mean.** Tail latency (max/p90) can suffer. Cost could use sum of squares.
* Boarding/door time, acceleration and floor-skipping speed are ignored (spec: 1 floor = 1 unit).
* One-shot flow: the sim runs a fixed request list rather than a live stream (the `RequestFeed` abstraction makes streaming straightforward).

---

# Interview prep

## Likely follow-up questions (and short answers)

1. **Why not just send the nearest car?** Ignores direction, load and who is already on board. Baseline comparison above shows ~40% worse averages.
2. **What's the time complexity?** Per request: E cars x O(S) projection steps, where S is stops/ticks until the car empties. Total O(R x E x S). Could cache the baseline projection per car per tick (it doesn't change between assignments at the same tick unless a passenger was just added).
3. **Is it optimal?** No: greedy/online. Optimal assignment is a NP-hard-flavored scheduling problem (dial-a-ride). Greedy with a good cost function is the industry norm; compare against an offline lower bound to measure the gap.
4. **Can anyone starve?** Discuss above; mention aging term.
5. **How do you handle a full elevator that is passing a waiting passenger?** Pickups aren't targets while full; passenger stays assigned and gets picked up on a later sweep; the cost function already priced that delay in.
6. **What if a car breaks / a floor is closed?** Mark the car out of service, re-run the assignment for its *waiting* passengers (riders are stuck), which relaxes the "assignment is final" rule. Needs product input.
7. **How would you scale to 100 floors / 20 cars / thousands of requests per minute?** Zoning (low/mid/high banks), cap the projection horizon, cache baselines, only evaluate the k most promising cars, move to incremental route data structures.
8. **How do you validate it?** Unit tests for invariants (capacity, one-floor-per-tick, direction rule, everyone served), property/randomized tests, comparison against baselines, regression on recorded real traffic.
9. **What would you change for real-world use?** Door time, acceleration, group arrivals, VIP/freight modes, energy cost, fairness SLAs, predictive pre-positioning (idle cars parking at the lobby at 8:55am), live streaming input.
10. **What metric should we optimize?** Average vs p95 wait vs max wait is a *business* decision. Ask who the user is (office tower, hospital, hotel).
11. **Same-tick requests?** Assigned sequentially in input order; each sees the previous ones.
12. **Why a `Scheduler` interface?** Swap algorithms (nearest, zoning, ML-based) and A/B them on the same input.

## FDE priorities for this system
An FDE is the person who gets this working in the customer's building, so the priorities differ from a pure algorithms exercise:

1. **Clarify the real objective first.** Average wait? Worst-case wait? Energy? Accessibility? Ask before optimizing. The spec's three goals can conflict.
2. **Correctness and safety invariants over cleverness.** Capacity never exceeded, nobody lost, simulation terminates. Encode them as tests.
3. **Ship a simple, explainable baseline, then iterate with data.** Nearest-car baseline -> cost-based dispatch -> measure -> improve. Always show a before/after number.
4. **Observability.** The position log, per-passenger timestamps, percentiles, utilization. Customers will ask "why did my elevator take so long?" and you need to answer with data.
5. **Realistic input.** Real traffic is bursty (morning up-peak, lunch, evening down-peak). Build generators for these, or replay customer logs.
6. **Configuration without code changes.** Elevator count, floors, capacity, scheduler choice are all parameters; extend to per-car limits, restricted floors, out-of-service cars.
7. **Failure modes and fallbacks.** Bad input rejected with clear messages; deadlock guard; what happens if the dispatcher crashes (cars fall back to a simple local mode).
8. **Communicate trade-offs to non-engineers.** "This cuts average wait ~40% but a few people wait longer; here's the knob."
9. **Fit into the customer's systems.** Integration with building management/access control, data formats, deployment, ongoing monitoring.
