"""Tests for the operator's control cycle, against the simulated tub and a fake API."""

import os
import tempfile
import unittest

from support import ServerThread

import controller
from api_client import ApiClient, ApiError
from bwa.client import Client
from bwa.messages.status import HeatingMode, TemperatureRange, TemperatureScale
from controller import StateFile, run_cycle

OFF = {"heating_mode": "rest", "temperature_range": "low", "set_temperature": 50}


def on(temperature):
    return {"heating_mode": "ready", "temperature_range": "high", "set_temperature": temperature}


class FakeApi:
    """Behaves like the real API's operator endpoints, in memory."""

    def __init__(self, desired=None):
        self.desired = desired
        self.version = None if desired is None else 1
        self.source = None if desired is None else "ui"
        self.reports = []
        self.fail_reports = False
        self.ui_change_during_report = None

    def ui_sets(self, desired):
        self.desired, self.source = desired, "ui"
        self.version = (self.version or 0) + 1

    def get_desired(self):
        return {"desired": self.desired, "desired_version": self.version}

    def report(self, tub, panel_change=False, desired_version=None):
        if self.fail_reports:
            raise ApiError("report failed")
        self.reports.append(tub)
        if self.ui_change_during_report is not None:
            self.ui_sets(self.ui_change_during_report)
            self.ui_change_during_report = None
        adopted = False
        if panel_change and desired_version == self.version:
            self.desired = {
                "heating_mode": "ready" if tub["heating_mode"] == "ready" else "rest",
                "temperature_range": tub["temperature_range"],
                "set_temperature": tub["set_temperature"],
            }
            self.source = "panel"
            self.version = (self.version or 0) + 1
            adopted = True
        return {"adopted": adopted, "desired": self.desired, "desired_version": self.version}


class ControllerTestCase(unittest.TestCase):

    def setUp(self):
        controller.CONFIRM_TIMEOUT = 1.0
        self.srv = ServerThread()
        self.srv.__enter__()
        self.addCleanup(self.srv.__exit__)
        self.tub = self.srv.status          # the simulated tub: ready, high, 102
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = StateFile(os.path.join(tmp.name, "state.json"))

    def connect(self):
        return Client("127.0.0.1", self.srv.port, timeout=2.0)

    def cycle(self, api, **kwargs):
        return run_cycle(api, self.connect, self.state, **kwargs)

    def tub_controls(self):
        return controller.control_state(self.tub)


class TestApplyingDesiredState(ControllerTestCase):

    def test_in_step_changes_nothing(self):
        api = FakeApi(on(102))
        self.assertEqual(self.cycle(api), "in-step")
        self.assertEqual(self.tub_controls(), on(102))
        self.assertEqual(api.reports[-1]["current_temperature"], 100.0)

    def test_changes_set_temperature(self):
        for temperature in (104, 105, 106):
            api = FakeApi(on(temperature))
            self.assertEqual(self.cycle(api), "changed")
            self.assertEqual(self.tub_controls(), on(temperature))
            self.assertEqual(api.reports[-1]["set_temperature"], temperature)

    def test_turns_off_and_back_on(self):
        api = FakeApi(OFF)
        self.assertEqual(self.cycle(api), "changed")
        self.assertEqual(self.tub_controls(), OFF)
        self.assertEqual(self.tub.heating_mode, HeatingMode.REST)
        self.assertEqual(self.tub.temperature_range, TemperatureRange.LOW)

        api.ui_sets(on(105))
        self.assertEqual(self.cycle(api), "changed")
        self.assertEqual(self.tub_controls(), on(105))
        self.assertEqual(api.source, "ui")

    def test_ready_in_rest_counts_as_rest(self):
        api = FakeApi(OFF)
        self.cycle(api)
        self.tub.heating_mode = HeatingMode.READY_IN_REST   # someone turned the jets on
        self.assertEqual(self.cycle(api), "in-step")
        self.assertEqual(api.source, "ui")
        self.assertEqual(api.reports[-1]["heating_mode"], "ready_in_rest")

    def test_rejected_change_is_retried_not_mistaken_for_panel(self):
        api = FakeApi(on(104))
        self.cycle(api)
        # 120 is outside the tub's range; it ignores the request.
        api.ui_sets(on(120))
        self.assertEqual(self.cycle(api), "change-failed")
        self.assertEqual(self.tub_controls(), on(104))
        self.assertEqual(self.cycle(api), "change-failed")
        self.assertEqual(api.desired, on(120))
        self.assertEqual(api.source, "ui")


class TestPanelChanges(ControllerTestCase):

    def test_panel_change_is_adopted_not_undone(self):
        api = FakeApi(on(104))
        self.cycle(api)
        self.tub.set_temperature = 100.0            # pressed "down" at the tub
        self.assertEqual(self.cycle(api), "panel-change")
        self.assertEqual(self.tub_controls(), on(100))
        self.assertEqual(api.desired, on(100))
        self.assertEqual(api.source, "panel")
        # and it stays that way
        self.assertEqual(self.cycle(api), "in-step")
        self.assertEqual(self.tub_controls(), on(100))

    def test_ui_change_after_panel_change_wins(self):
        api = FakeApi(on(104))
        self.cycle(api)
        self.tub.set_temperature = 100.0
        self.cycle(api)
        api.ui_sets(on(106))
        self.assertEqual(self.cycle(api), "changed")
        self.assertEqual(self.tub_controls(), on(106))
        self.assertEqual(api.source, "ui")

    def test_panel_change_after_ui_change_wins(self):
        api = FakeApi(on(104))
        self.cycle(api)
        api.ui_sets(on(106))
        self.cycle(api)
        self.tub.heating_mode = HeatingMode.REST    # switched to rest at the tub
        self.assertEqual(self.cycle(api), "panel-change")
        self.assertEqual(self.tub.heating_mode, HeatingMode.REST)
        self.assertEqual(api.desired["heating_mode"], "rest")

    def test_ui_change_racing_a_panel_report_wins(self):
        api = FakeApi(on(104))
        self.cycle(api)
        self.tub.set_temperature = 100.0
        # A user picks 106 after the operator read the desired state but
        # before its panel report arrives.
        api.ui_change_during_report = on(106)
        self.assertEqual(self.cycle(api), "changed")
        self.assertEqual(self.tub_controls(), on(106))
        self.assertEqual(api.desired, on(106))
        self.assertEqual(api.source, "ui")

    def test_new_system_starts_from_the_tub(self):
        api = FakeApi(desired=None)
        self.assertEqual(self.cycle(api), "panel-change")
        self.assertEqual(api.desired, on(102))
        self.assertEqual(self.tub_controls(), on(102))

    def test_lost_state_file_means_cloud_wins(self):
        api = FakeApi(on(104))
        self.tub.set_temperature = 100.0
        self.assertEqual(self.cycle(api), "changed")
        self.assertEqual(self.tub_controls(), on(104))

    def test_failed_report_after_our_change_is_not_a_panel_change(self):
        api = FakeApi(on(104))
        self.cycle(api)
        api.ui_sets(on(106))
        api.fail_reports = True
        with self.assertRaises(ApiError):
            self.cycle(api)
        self.assertEqual(self.tub_controls(), on(106))
        api.fail_reports = False
        self.assertEqual(self.cycle(api), "in-step")
        self.assertEqual(api.source, "ui")


class TestReportOnly(ControllerTestCase):

    def test_never_changes_tub_or_desired_state(self):
        api = FakeApi(on(106))
        self.assertEqual(self.cycle(api, report_only=True), "reported")
        self.tub.set_temperature = 100.0
        self.assertEqual(self.cycle(api, report_only=True), "reported")
        self.assertEqual(self.tub_controls(), on(100))
        self.assertEqual(api.desired, on(106))
        self.assertEqual(api.reports[-1]["set_temperature"], 100)


class TestFailures(ControllerTestCase):

    def test_tub_unreachable_is_reported(self):
        api = FakeApi(on(104))

        def refuse():
            raise ConnectionRefusedError("no tub")

        self.assertEqual(run_cycle(api, refuse, self.state), "tub-unreachable")
        self.assertEqual(api.reports, [None])

    def test_celsius_tub_is_left_alone(self):
        api = FakeApi(on(104))
        self.tub.temperature_scale = TemperatureScale.CELSIUS
        self.tub.set_temperature = 38.0
        self.assertEqual(self.cycle(api), "celsius")
        self.assertEqual(self.tub.set_temperature, 38.0)

    def test_api_down_leaves_tub_alone(self):
        class DownApi(FakeApi):
            def get_desired(self):
                raise ApiError("down")

        with self.assertRaises(ApiError):
            self.cycle(DownApi(on(106)))
        self.assertEqual(self.tub_controls(), on(102))

    def test_api_client_requires_https(self):
        with self.assertRaises(ValueError):
            ApiClient("http://example.com", "key")

    def test_state_file_survives_corruption(self):
        with open(self.state.path, "w") as f:
            f.write("{not json")
        self.assertEqual(self.state.load(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
