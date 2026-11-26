"""Requirement-level checks. Everything is verified from the OUTPUT (position log + passenger
timestamps), independently of the elevator's internal bookkeeping."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from elevator_sim import Request, simulate

CONFIGS = [(1, 8, 1), (2, 10, 2), (3, 20, 4), (4, 30, 6), (2, 5, 3)]   # (elevators, floors, capacity)


def make(n, floors, horizon, seed):
    rng = random.Random(seed)
    return [Request(rng.randint(0, horizon), f"p{i}", *rng.sample(range(1, floors + 1), 2))
            for i in range(n)]


class RequirementTests(unittest.TestCase):
    def runs(self):
        for seed in range(4):
            for e, f, c in CONFIGS:
                reqs = make(120, f, 60, seed)
                yield e, f, c, reqs, simulate(reqs, e, f, c)

    def test_req1_everyone_served_and_times_consistent(self):
        for e, f, c, reqs, r in self.runs():
            self.assertEqual(len(r.passengers), len(reqs))
            for p in r.passengers:
                self.assertIsNotNone(p.dropoff_time)
                self.assertGreaterEqual(p.pickup_time, p.request_time)
                self.assertEqual(p.total_time, p.wait_time + p.ride_time)
                self.assertGreaterEqual(p.total_time, p.ideal_time)   # can't beat a non-stop trip

    def test_req1_capacity_never_exceeded_from_log(self):
        for e, f, c, reqs, r in self.runs():
            for row in r.position_log:
                t = row[0]
                for k in range(e):
                    onboard = sum(1 for p in r.passengers
                                  if p.elevator_id == k and p.pickup_time <= t < p.dropoff_time)
                    self.assertLessEqual(onboard, c)

    def test_req1_direction_logic_from_log(self):
        # While a passenger is riding, their car must move exactly one floor per tick toward dest.
        for e, f, c, reqs, r in self.runs():
            log = r.position_log
            for p in r.passengers:
                col = 1 + p.elevator_id
                for t in range(p.pickup_time, p.dropoff_time):
                    self.assertEqual(log[t + 1][col] - log[t][col], p.direction)

    def test_req2_assignment_is_final_and_honored(self):
        # The car recorded at request time is the car that picked up at source and dropped at dest.
        for e, f, c, reqs, r in self.runs():
            log = r.position_log
            for p in r.passengers:
                col = 1 + p.elevator_id
                self.assertEqual(log[p.pickup_time][col], p.source)
                self.assertEqual(log[p.dropoff_time][col], p.dest)

    def test_req5_no_peeking(self):
        # Removing all FUTURE requests must not change anything that happened up to time T.
        T = 30
        for seed in range(4):
            reqs = make(100, 15, 80, seed)
            full = simulate(reqs, 3, 15, 4)
            part = simulate([q for q in reqs if q.time <= T], 3, 15, 4)
            upto = min(T, part.end_time)
            self.assertEqual(full.position_log[:upto + 1], part.position_log[:upto + 1])
            full_assign = {p.id: p.elevator_id for p in full.passengers}
            for p in part.passengers:
                self.assertEqual(p.elevator_id, full_assign[p.id])

    def test_req5_accepts_tuples_dicts_and_requests(self):
        as_req = [Request(10, "passenger3", 20, 1), Request(0, "a", 1, 5)]
        as_tup = [(10, "passenger3", 20, 1), (0, "a", 1, 5)]
        as_dic = [dict(time=10, id="passenger3", source=20, dest=1), dict(time=0, id="a", source=1, dest=5)]
        logs = [simulate(x, 2, 20, 4).position_log for x in (as_req, as_tup, as_dic)]
        self.assertEqual(logs[0], logs[1])
        self.assertEqual(logs[0], logs[2])

    def test_req4_configurable_sizes(self):
        for e, f, c in CONFIGS:
            r = simulate(make(10, f, 5, 1), e, f, c)
            self.assertEqual(len(r.elevators), e)
            self.assertTrue(all(1 <= x <= f for row in r.position_log for x in row[1:]))
            self.assertTrue(all(len(row) == e + 1 for row in r.position_log))


if __name__ == "__main__":
    unittest.main()
