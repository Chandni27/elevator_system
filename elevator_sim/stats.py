"""Passenger and elevator statistics."""
from __future__ import annotations

import math
import statistics
from typing import Dict, List

from .simulation import SimulationResult


def describe(values: List[float]) -> Dict[str, float]:
    s = sorted(values)
    n = len(s)
    return {
        "min": s[0],
        "max": s[-1],
        "avg": sum(s) / n,
        "median": statistics.median(s),
        "p90": s[min(n - 1, math.ceil(0.9 * n) - 1)],
        "stdev": statistics.pstdev(s),
    }


def _histogram(values: List[int], buckets: int = 5, width_chars: int = 30) -> List[str]:
    top = max(values)
    step = max(1, math.ceil((top + 1) / buckets))
    counts = [0] * buckets
    for v in values:
        counts[min(v // step, buckets - 1)] += 1
    biggest = max(counts)
    lines = []
    for i, n in enumerate(counts):
        lo, hi = i * step, (i + 1) * step - 1
        label = f"{lo}-{hi}" if i < buckets - 1 else f"{lo}+"
        bar = "#" * round(width_chars * n / biggest) if biggest else ""
        lines.append(f"    {label:>7} | {bar} {n}")
    return lines


def build_report(result: SimulationResult) -> str:
    ps = result.passengers
    if not ps:
        return "No passengers were simulated."

    waits = [p.wait_time for p in ps]
    rides = [p.ride_time for p in ps]
    totals = [p.total_time for p in ps]
    w, r, t = describe(waits), describe(rides), describe(totals)

    out: List[str] = []
    out.append("=" * 62)
    out.append("PASSENGER SUMMARY  (1 time unit = 1 floor of travel)")
    out.append("=" * 62)
    out.append(f"Passengers served : {len(ps)}")
    out.append(f"Simulation ended  : t = {result.end_time}")
    out.append("")
    out.append(f"{'':8}{'min':>7}{'max':>7}{'avg':>8}{'median':>8}{'p90':>7}{'stdev':>8}")
    for name, d in (("wait", w), ("ride", r), ("total", t)):
        out.append(f"{name:8}{d['min']:>7.0f}{d['max']:>7.0f}{d['avg']:>8.2f}"
                   f"{d['median']:>8.1f}{d['p90']:>7.0f}{d['stdev']:>8.2f}")

    # ---- notable observations
    out.append("")
    out.append("NOTABLE OBSERVATIONS")
    zero = sum(1 for x in waits if x == 0)
    out.append(f"- {100 * zero / len(ps):.0f}% of passengers boarded with zero wait.")
    worst = max(ps, key=lambda p: p.wait_time)
    out.append(f"- Longest wait: {worst.id} waited {worst.wait_time} (requested t={worst.request_time}, "
               f"floor {worst.source}->{worst.dest}, elevator {worst.elevator_id}).")
    if w["avg"] > 0:
        ratio = w["max"] / w["avg"]
        note = "  <- long tail: a few passengers are being starved relative to the rest" if ratio > 4 else ""
        out.append(f"- Max wait is {ratio:.1f}x the average wait.{note}")
    ideal_total = sum(p.ideal_time for p in ps)
    out.append(f"- Average total time is {t['avg']:.1f} vs {ideal_total / len(ps):.1f} "
               f"for an ideal non-stop trip (+{t['avg'] - ideal_total / len(ps):.1f} overhead).")
    detour = sum(rides) / max(1, ideal_total)
    out.append(f"- Riders spend {detour:.2f}x the direct distance in the car "
               f"(extra stops for other passengers).")
    out.append(f"- Wait share of total time: {100 * sum(waits) / sum(totals):.0f}% "
               f"(the part the dispatcher can influence most).")

    out.append("")
    out.append("WAIT TIME DISTRIBUTION")
    out.extend(_histogram(waits))

    # ---- per-elevator view
    out.append("")
    out.append("ELEVATORS")
    out.append(f"{'id':>4}{'served':>8}{'floors moved':>14}{'utilisation':>13}{'peak load':>11}")
    for e in result.elevators:
        util = e.floors_travelled / max(1, result.end_time)
        out.append(f"{e.id:>4}{e.delivered:>8}{e.floors_travelled:>14}{util:>12.0%}{e.max_load:>8}/{e.capacity}")
    counts = [e.delivered for e in result.elevators]
    if len(counts) > 1 and sum(counts):
        out.append(f"- Load balance: busiest car served {max(counts)}, quietest {min(counts)}.")
    return "\n".join(out)
