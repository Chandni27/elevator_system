"""Command-line runner.

Examples
--------
  python main.py --requests sample_requests.csv
  python main.py --random 200 --seed 7 --elevators 4 --floors 30 --capacity 6
  python main.py --random 200 --pattern rush --compare
"""
import argparse
import csv
import random
import sys
from typing import List

from elevator_sim import SCHEDULERS, Config, Request, Simulation, build_report


def load_requests(path: str) -> List[Request]:
    """CSV with columns time,id,source,dest (header row optional)."""
    reqs = []
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or not row[0].strip().lstrip("-").isdigit():
                continue  # header / blank line
            t, pid, src, dst = (x.strip() for x in row[:4])
            reqs.append(Request(int(t), pid, int(src), int(dst)))
    return reqs


def generate_requests(n: int, floors: int, horizon: int, seed: int, pattern: str) -> List[Request]:
    rng = random.Random(seed)
    reqs = []
    for i in range(n):
        if pattern == "rush" and rng.random() < 0.6:       # morning rush: most trips start at lobby
            src, dst = 1, rng.randint(2, floors)
        else:
            src, dst = rng.sample(range(1, floors + 1), 2)
        reqs.append(Request(rng.randint(0, horizon), f"passenger{i + 1}", src, dst))
    return reqs


def main() -> int:
    ap = argparse.ArgumentParser(description="Destination-dispatch elevator simulation")
    ap.add_argument("--requests", help="CSV file: time,id,source,dest")
    ap.add_argument("--random", type=int, metavar="N", help="generate N random requests instead")
    ap.add_argument("--pattern", choices=["uniform", "rush"], default="uniform")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--horizon", type=int, default=200, help="latest request time for --random")
    ap.add_argument("--elevators", type=int, default=3)
    ap.add_argument("--floors", type=int, default=20)
    ap.add_argument("--capacity", type=int, default=4)
    ap.add_argument("--scheduler", choices=SCHEDULERS, default="dispatch")
    ap.add_argument("--log", default="elevator_positions.csv", help="position log output file")
    ap.add_argument("--compare", action="store_true", help="also run the naive nearest-car baseline")
    a = ap.parse_args()

    if a.random:
        reqs = generate_requests(a.random, a.floors, a.horizon, a.seed, a.pattern)
    elif a.requests:
        reqs = load_requests(a.requests)
    else:
        ap.error("give --requests FILE or --random N")

    cfg = Config(a.elevators, a.floors, a.capacity)
    result = Simulation(cfg, SCHEDULERS[a.scheduler]()).run(reqs, log_path=a.log)
    print(build_report(result))
    print(f"\nPosition log written to {a.log} ({len(result.position_log)} rows)")

    if a.compare:
        print("\n" + "=" * 62 + "\nSCHEDULER COMPARISON (same requests)\n" + "=" * 62)
        print(f"{'scheduler':12}{'avg wait':>10}{'max wait':>10}{'avg total':>11}{'max total':>11}{'end t':>8}")
        for name, cls in SCHEDULERS.items():
            r = Simulation(cfg, cls()).run(reqs)
            w = [p.wait_time for p in r.passengers]
            t = [p.total_time for p in r.passengers]
            print(f"{name:12}{sum(w)/len(w):>10.2f}{max(w):>10}{sum(t)/len(t):>11.2f}{max(t):>11}{r.end_time:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
