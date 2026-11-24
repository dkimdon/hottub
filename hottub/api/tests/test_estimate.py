"""Tests for the heating estimate: the pure calculation, then GET /tub."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "function"))

import estimate  # noqa: E402
from test_api import ApiTestCase  # noqa: E402

NOW = datetime(2026, 11, 23, 22, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def readings(start_minutes_ago, temperatures, heating=True, step=2, now=NOW):
    """One reading every `step` minutes, starting `start_minutes_ago`."""
    return [
        {"at": iso(now - timedelta(minutes=start_minutes_ago - i * step)),
         "temperature": t, "heating": heating}
        for i, t in enumerate(temperatures)
    ]


def climbing(minutes, rate_per_hour, start=90.0, step=2):
    """Whole-degree readings of a tub heating at a steady rate, as the tub reports them."""
    count = minutes // step + 1
    return [int(start + rate_per_hour * i * step / 60) for i in range(count)]


class TestCalculation(unittest.TestCase):

    def test_rate_of_a_steady_run(self):
        run = readings(120, climbing(120, 4.0))
        self.assertAlmostEqual(estimate.current_rate(run), 4.0, delta=0.3)

    def test_short_run_is_not_measured(self):
        run = readings(30, climbing(30, 4.0))
        self.assertIsNone(estimate.current_rate(run))

    def test_run_that_barely_rises_is_not_measured(self):
        run = readings(60, [100] * 30 + [101])
        self.assertIsNone(estimate.current_rate(run))

    def test_finished_run_is_not_current(self):
        run = readings(120, climbing(100, 4.0)) + readings(18, [97] * 10, heating=False)
        self.assertIsNone(estimate.current_rate(run))

    def test_gap_splits_runs(self):
        # Two 30-minute runs an hour apart: neither is long enough alone.
        run = readings(150, climbing(30, 4.0)) + readings(30, climbing(30, 4.0, start=95))
        self.assertIsNone(estimate.current_rate(run))

    def test_rate_is_kept_within_sensible_bounds(self):
        run = readings(60, climbing(60, 40.0))
        self.assertEqual(estimate.current_rate(run), estimate.MAX_RATE)

    def test_learned_rate_weights_longer_runs(self):
        week = (
            readings(3000, climbing(180, 3.0))                       # 3 h at 3 °F/h
            + readings(2000, [95] * 5, heating=False)
            + readings(1000, climbing(60, 6.0, start=80))            # 1 h at 6 °F/h
        )
        self.assertAlmostEqual(estimate.learned_rate(week), 3.75, delta=0.4)

    def test_learned_rate_without_runs(self):
        self.assertIsNone(estimate.learned_rate(readings(60, [100] * 30, heating=False)))

    def test_estimate(self):
        result = estimate.estimate(104, 100, iso(NOW - timedelta(minutes=2)), 4.0, "typical", NOW)
        self.assertEqual(result["ready_at"], iso(NOW + timedelta(minutes=58)))
        self.assertEqual(result["rate_per_hour"], 4.0)
        self.assertEqual(result["based_on"], "typical")

    def test_no_estimate_at_or_above_target(self):
        measured = iso(NOW)
        self.assertIsNone(estimate.estimate(104, 104, measured, 4.0, "typical", NOW))
        self.assertIsNone(estimate.estimate(104, 105, measured, 4.0, "typical", NOW))

    def test_no_estimate_from_an_old_reading(self):
        measured = iso(NOW - timedelta(minutes=estimate.STALE_MINUTES + 1))
        self.assertIsNone(estimate.estimate(104, 100, measured, 4.0, "typical", NOW))


class TestTubEstimate(ApiTestCase):

    def add(self, items):
        table = boto3.resource("dynamodb").Table("hottub-history-unit")
        for item in items:
            table.put_item(Item={**item, "kind": "temperature"})

    def tub(self):
        return self.call("GET /tub", user=self.bob)[1]

    def test_typical_rate_before_any_history(self):
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.report(tub={"current_temperature": 100})
        result = self.tub()["heating_estimate"]
        self.assertEqual(result["based_on"], "typical")
        self.assertEqual(result["rate_per_hour"], estimate.DEFAULT_RATE)

    def test_rate_from_the_heating_in_progress(self):
        now = datetime.now(timezone.utc)
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.add(readings(120, climbing(116, 3.0, start=92), now=now))
        self.report(tub={"current_temperature": 97, "heating": True})
        result = self.tub()["heating_estimate"]
        self.assertEqual(result["based_on"], "this_heating")
        self.assertAlmostEqual(result["rate_per_hour"], 3.0, delta=0.4)

    def test_rate_from_the_past_week(self):
        now = datetime.now(timezone.utc)
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.add(readings(60 * 48, climbing(180, 5.0, start=80), now=now))
        self.report(tub={"current_temperature": 100})
        result = self.tub()["heating_estimate"]
        self.assertEqual(result["based_on"], "past_week")
        self.assertAlmostEqual(result["rate_per_hour"], 5.0, delta=0.4)
        # The week's rate is kept, so the next request does not query it again.
        self.assertEqual(self.tub()["heating_estimate"]["based_on"], "past_week")

    def test_no_estimate_when_off_or_at_temperature(self):
        self.report(tub={"current_temperature": 100})
        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.bob)
        self.assertIsNone(self.tub()["heating_estimate"])
        self.call("PUT /tub/setpoint", {"setpoint": 102}, user=self.bob)
        self.report(tub={"current_temperature": 102})
        self.assertIsNone(self.tub()["heating_estimate"])

    def test_history_failure_gives_no_estimate_but_still_works(self):
        self.call("PUT /tub/setpoint", {"setpoint": 104}, user=self.bob)
        self.report(tub={"current_temperature": 100})
        boto3.client("dynamodb").delete_table(TableName="hottub-history-unit")
        status, body = self.call("GET /tub", user=self.bob)
        self.assertEqual(status, 200)
        self.assertIsNone(body["heating_estimate"])


if __name__ == "__main__":
    unittest.main()
