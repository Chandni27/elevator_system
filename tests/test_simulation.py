import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from elevator_sim import Config, Request, Simulation, simulate
from elevator_sim.simulation import RequestFeed


def random_requests(n, floors, horizon, seed):
    rng = random.Random(seed)
    return [Request(rng.randint(0, horizon), f"p{i}", *rng.sample(range(1, floors + 1), 2))
            for i in range(n)]


class ElevatorSimTests(unittest.TestCase):
    def test_single_passenger_exact_timing(self):
        # Car starts at floor 1. 1->5 takes 4 units, 5->2 takes 3 more.
        r = simulate([Request(0, "a", 5, 2)], 1, 10, 4)
        p = r.passengers[0]
        self.assertEqual((p.wait_time, p.ride_time, p.total_time), (4, 3, 7))

    def test_everyone_is_served_and_capacity_respected(self):
        reqs = random_requests(300, 25, 150, seed=3)
        r = simulate(reqs, 3, 25, 3)
        self.assertEqual(len(r.passengers), 300)
        self.assertTrue(all(p.dropoff_time is not None for p in r.passengers))
        self.assertTrue(all(e.max_load <= 3 for e in r.elevators))

    def test_capacity_one_still_finishes(self):
        r = simulate(random_requests(60, 10, 5, seed=9), 2, 10, 1)
        self.assertTrue(all(p.dropoff_time is not None for p in r.passengers))

    def test_direction_rule(self):
        # A rides 1->10. B (5->2, going DOWN) must not hop on while the car is going UP.
        reqs = [Request(0, "A", 1, 10), Request(1, "B", 5, 2)]
        r = simulate(reqs, 1, 10, 4)
        a, b = {p.id: p for p in r.passengers}.values()
        self.assertGreaterEqual(b.pickup_time, a.dropoff_time)
        self.assertEqual((b.pickup_time, b.dropoff_time), (14, 17))

    def test_assignment_is_final(self):
        r = simulate(random_requests(80, 15, 40, seed=5), 3, 15, 4)
        served_by = {e.id: e.delivered for e in r.elevators}
        self.assertEqual(sum(served_by.values()), 80)

    def test_feed_does_not_peek(self):
        feed = RequestFeed([Request(10, "late", 1, 2), Request(3, "early", 1, 2)])
        self.assertEqual(feed.poll(2), [])
        self.assertEqual([q.id for q in feed.poll(3)], ["early"])
        self.assertEqual(feed.poll(9), [])
        self.assertEqual([q.id for q in feed.poll(10)], ["late"])

    def test_log_has_row_per_tick_and_moves_one_floor_max(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.csv")
            r = simulate([Request(0, "a", 3, 9), Request(40, "b", 9, 1)], 2, 10, 4, log_path=path)
            self.assertEqual([row[0] for row in r.position_log], list(range(r.end_time + 1)))
            for prev, cur in zip(r.position_log, r.position_log[1:]):
                for a, b in zip(prev[1:], cur[1:]):
                    self.assertLessEqual(abs(a - b), 1)
            with open(path) as f:
                self.assertEqual(len(f.read().strip().splitlines()), r.end_time + 2)  # + header

    def test_idle_gap_is_ticked_through(self):
        r = simulate([Request(0, "a", 1, 2), Request(100, "b", 1, 2)], 1, 5, 2)
        self.assertEqual(len(r.position_log), r.end_time + 1)
        self.assertGreaterEqual(r.end_time, 101)

    def test_invalid_requests_rejected(self):
        for bad in (Request(0, "x", 1, 1), Request(0, "x", 0, 5), Request(0, "x", 1, 99), Request(-1, "x", 1, 2)):
            with self.assertRaises(ValueError):
                simulate([bad], 1, 10, 2)
        with self.assertRaises(ValueError):
            simulate([Request(0, "x", 1, 2), Request(1, "x", 2, 3)], 1, 10, 2)


if __name__ == "__main__":
    unittest.main()
