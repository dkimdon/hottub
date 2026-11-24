"""Tests for the timer: "have it at 104 °F by 7 PM"."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import boto3

from test_api import ApiTestCase


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def in_minutes(minutes):
    return iso(datetime.now(timezone.utc) + timedelta(minutes=minutes))


class TimerTestCase(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.tub = sys.modules["tub"]
        # Most tests must not depend on whether they run during the
        # midnight turn-off hour; the tests of that hour patch it back.
        patcher = mock.patch.object(self.tub, "_quiet_hour", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_timer(self, setpoint, ready_at, user=None):
        return self.call("PUT /tub/timer", {"setpoint": setpoint, "ready_at": ready_at}, user=user or self.bob)

    def state(self):
        return self.call("GET /tub", user=self.bob)[1]

    def desired(self):
        return self.operator("GET /operator/desired")[1]


class TestSettingTimers(TimerTestCase):

    def test_requires_sign_in(self):
        self.assertEqual(self.call("PUT /tub/timer", {"setpoint": 104, "ready_at": in_minutes(120)})[0], 401)
        self.assertEqual(self.call("DELETE /tub/timer")[0], 401)

    def test_set_and_show(self):
        self.report(tub={"current_temperature": 90, "heating_mode": "rest"})
        ready = in_minutes(300)
        status, body = self.set_timer(104, ready)
        self.assertEqual(status, 200)
        timer = self.state()["timer"]
        self.assertEqual(timer["setpoint"], "104")
        self.assertEqual(timer["ready_at"], ready)
        self.assertEqual(timer["set_by"], "bob@example.com")
        # 14 °F at the typical 4 °F an hour, plus the margin.
        expected = datetime.now(timezone.utc) + timedelta(minutes=300 - 210 - self.tub.TIMER_MARGIN_MINUTES)
        starts = datetime.strptime(timer["starts_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((starts - expected).total_seconds()), 90)

    def test_accepts_milliseconds_and_offsets(self):
        when = datetime.now(timezone.utc) + timedelta(hours=3)
        self.assertEqual(self.set_timer("105", when.isoformat(timespec="milliseconds"))[0], 200)
        self.assertEqual(self.set_timer(105, when.astimezone(timezone(timedelta(hours=-8))).isoformat())[0], 200)

    def test_invalid_timers(self):
        for setpoint, ready_at in [
            (101, in_minutes(120)),       # not an offered temperature
            ("off", in_minutes(120)),     # a timer is for heating
            (True, in_minutes(120)),
            (104, in_minutes(5)),         # too soon
            (104, in_minutes(-60)),       # in the past
            (104, in_minutes(60 * 49)),   # too far ahead
            (104, "tomorrow at seven"),
            (104, "2026-11-24T03:00:00"),  # no time zone
            (104, None),
        ]:
            with self.subTest(setpoint=setpoint, ready_at=ready_at):
                self.assertEqual(self.set_timer(setpoint, ready_at)[0], 400)
        self.assertIsNone(self.state()["timer"])

    def test_a_new_timer_replaces_the_old_one(self):
        self.set_timer(104, in_minutes(300))
        self.set_timer(106, in_minutes(400), user=self.alice)
        timer = self.state()["timer"]
        self.assertEqual((timer["setpoint"], timer["set_by"]), ("106", "alice@example.com"))

    def test_cancel(self):
        self.set_timer(104, in_minutes(300))
        self.assertEqual(self.call("DELETE /tub/timer", user=self.alice)[0], 200)
        self.assertIsNone(self.state()["timer"])
        self.assertEqual(self.call("DELETE /tub/timer", user=self.alice)[0], 200)  # harmless twice


class TestTimerStartsHeating(TimerTestCase):

    def test_waits_until_it_is_time(self):
        self.report(tub={"current_temperature": 90, "heating_mode": "rest", "set_temperature": 50,
                         "temperature_range": "low"})
        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.alice)
        self.set_timer(104, in_minutes(60 * 20))
        self.assertEqual(self.desired()["desired"]["heating_mode"], "rest")
        self.assertIsNotNone(self.state()["timer"])

    def test_starts_heating_when_it_is_time(self):
        self.report(tub={"current_temperature": 100})
        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.alice)
        # 4 °F at 4 °F an hour is an hour; ready in 30 minutes means start now.
        self.set_timer(104, in_minutes(30))

        desired = self.desired()["desired"]
        self.assertEqual(desired, {"heating_mode": "ready", "temperature_range": "high", "set_temperature": 104})
        state = self.state()
        self.assertEqual(state["setpoint"], "104")
        self.assertEqual(state["setpoint_source"], "timer")
        self.assertEqual(state["setpoint_changed_by"], "bob@example.com")
        self.assertIsNone(state["timer"])
        changes = self.call("GET /history", user=self.bob)[1]["changes"]
        self.assertEqual((changes[0]["setpoint"], changes[0]["source"]), ("104", "timer"))

    def test_starts_only_once(self):
        self.report(tub={"current_temperature": 100})
        self.set_timer(104, in_minutes(30))
        first = self.desired()["desired_version"]
        self.assertEqual(self.desired()["desired_version"], first)

    def test_missed_timer_is_dropped(self):
        self.report(tub={"current_temperature": 100})
        self.set_timer(104, in_minutes(30))
        table = boto3.resource("dynamodb").Table("hottub-unit")
        table.update_item(Key={"id": "tub"}, UpdateExpression="SET timer_ready_at = :r",
                          ExpressionAttributeValues={":r": in_minutes(-90)})
        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.alice)
        self.assertEqual(self.desired()["desired"]["heating_mode"], "rest")
        self.assertIsNone(self.state()["timer"])

    def test_does_not_start_during_the_turn_off_hour(self):
        self.report(tub={"current_temperature": 100})
        self.call("PUT /tub/setpoint", {"setpoint": "off"}, user=self.alice)
        self.set_timer(104, in_minutes(30))
        with mock.patch.object(self.tub, "_quiet_hour", return_value=True):
            self.assertEqual(self.desired()["desired"]["heating_mode"], "rest")
        self.assertEqual(self.desired()["desired"]["heating_mode"], "ready")


class TestPacificTime(unittest.TestCase):

    def setUp(self):
        sys.modules.pop("tub", None)
        import os
        os.environ.setdefault("TABLE_NAME", "unused")
        os.environ.setdefault("HISTORY_TABLE_NAME", "unused")
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
        import tub
        self.tub = tub

    def test_standard_and_daylight_time(self):
        winter = datetime(2026, 1, 15, 8, 30, tzinfo=timezone.utc)
        summer = datetime(2026, 7, 15, 7, 30, tzinfo=timezone.utc)
        self.assertEqual(self.tub._pacific(winter).hour, 0)   # 00:30 PST
        self.assertEqual(self.tub._pacific(summer).hour, 0)   # 00:30 PDT
        self.assertTrue(self.tub._quiet_hour(winter))
        self.assertTrue(self.tub._quiet_hour(summer))
        self.assertFalse(self.tub._quiet_hour(winter + timedelta(hours=1)))

    def test_changeover_days(self):
        # 2026: daylight time from Sunday 8 March to Sunday 1 November.
        self.assertEqual(self.tub._pacific(datetime(2026, 3, 8, 9, 59, tzinfo=timezone.utc)).hour, 1)
        self.assertEqual(self.tub._pacific(datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)).hour, 3)
        self.assertEqual(self.tub._pacific(datetime(2026, 11, 1, 8, 59, tzinfo=timezone.utc)).hour, 1)
        self.assertEqual(self.tub._pacific(datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)).hour, 1)


if __name__ == "__main__":
    unittest.main()
