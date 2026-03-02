"""Live integration tests against a real Balboa spa on the local network.

These tests actually connect to the tub, read real status messages, and make
small changes (toggling lights, adjusting temperature briefly) to verify the
full end-to-end path of the library.

Run with:
    python -m pytest tests/test_live.py -v
or:
    python tests/test_live.py

The tests restore the tub to its original state after each test.
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bwa.client import Client
from bwa.discovery import find_spa, discover
from bwa.messages.status import Status, TemperatureScale


# ---------------------------------------------------------------------------
# Discover the spa once for the whole test session
# ---------------------------------------------------------------------------

SPA_IP = None

def get_spa_ip() -> str:
    global SPA_IP
    if SPA_IP is None:
        print("\n[live] Discovering spa on local network...", flush=True)
        SPA_IP = find_spa(timeout=5.0)
        if SPA_IP is None:
            raise RuntimeError(
                "No spa found on the network. "
                "Set SPA_IP manually if discovery is unreliable."
            )
        print(f"[live] Found spa at {SPA_IP}", flush=True)
    return SPA_IP


def get_status(spa: Client, retries: int = 5) -> Status:
    """Poll until we get a Status message."""
    for _ in range(retries):
        s = spa.poll_until_status(timeout=3.0)
        if s is not None:
            return s
    raise RuntimeError("Could not get a status message from the spa")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiscovery(unittest.TestCase):

    def test_discover_finds_spa(self):
        """UDP discovery should find at least one spa."""
        spas = discover(timeout=5.0)
        self.assertGreater(len(spas), 0, "No spa found via UDP discovery")
        for ip, name in spas.items():
            print(f"  Discovered: {name} @ {ip}")

    def test_find_spa_returns_ip(self):
        ip = get_spa_ip()
        self.assertIsNotNone(ip)
        # Rough IPv4 sanity check
        parts = ip.split(".")
        self.assertEqual(len(parts), 4)


class TestConnection(unittest.TestCase):

    def test_connect_and_get_status(self):
        """Should be able to connect and receive at least one Status message."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            status = get_status(spa)
        self.assertIsInstance(status, Status)
        print(f"\n  {status}")

    def test_status_temperatures_are_sane(self):
        """Current and set temperatures should be in a plausible range."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            status = get_status(spa)

        if status.temperature_scale == TemperatureScale.FAHRENHEIT:
            if status.current_temperature is not None:
                self.assertGreater(status.current_temperature, 50)
                self.assertLess(status.current_temperature, 115)
            self.assertGreater(status.set_temperature, 50)
            self.assertLess(status.set_temperature, 115)
        else:
            if status.current_temperature is not None:
                self.assertGreater(status.current_temperature, 10)
                self.assertLess(status.current_temperature, 45)
            self.assertGreater(status.set_temperature, 10)
            self.assertLess(status.set_temperature, 45)

    def test_status_time_is_sane(self):
        """Hour and minute from the tub should be valid clock values."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            status = get_status(spa)
        self.assertGreaterEqual(status.hour, 0)
        self.assertLessEqual(status.hour, 23)
        self.assertGreaterEqual(status.minute, 0)
        self.assertLessEqual(status.minute, 59)

    def test_multiple_status_messages(self):
        """The spa should send status every ~1 second; receive at least 3."""
        ip = get_spa_ip()
        received = []
        with Client(ip) as spa:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and len(received) < 3:
                s = spa.poll_until_status(timeout=2.0)
                if s is not None:
                    received.append(s)
        self.assertGreaterEqual(len(received), 3, "Expected at least 3 status messages in 5s")

    def test_request_configuration(self):
        """Sending a configuration request should not break the connection."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            spa.request_configuration()
            # Drain responses for 2 seconds, then verify status still arrives
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if spa.messages_pending():
                    spa.poll()
                else:
                    time.sleep(0.1)
            status = get_status(spa)
        self.assertIsNotNone(status)


def _pick_alternate_temp(status: Status) -> float:
    """Pick a valid temperature that differs from the current set_temperature.

    Respects the tub's current temperature range so the command is accepted.
    """
    from bwa.messages.status import TemperatureRange
    orig = status.set_temperature
    scale = status.temperature_scale
    rng = status.temperature_range

    if scale == TemperatureScale.FAHRENHEIT:
        if rng == TemperatureRange.HIGH:
            candidates = [103.0, 102.0, 101.0, 100.0]
        else:
            candidates = [79.0, 78.0, 77.0, 76.0]
    else:
        if rng == TemperatureRange.HIGH:
            candidates = [39.5, 39.0, 38.5, 38.0]
        else:
            candidates = [25.5, 25.0, 24.5, 24.0]

    for t in candidates:
        if abs(t - orig) > 0.4:
            return t
    return candidates[0]


def _poll_for_temperature(spa: Client, target: float, timeout: float = 5.0) -> float:
    """Poll status messages until one matches target (within 0.5°), or timeout.

    Returns the last observed set_temperature.
    """
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        s = spa.poll_until_status(timeout=1.5)
        if s is not None:
            last = s.set_temperature
            if abs(last - target) < 0.5:
                return last
    return last


class TestTemperatureControl(unittest.TestCase):
    """Tests that change the set-point and restore it.

    These tests are range-aware: they only set temperatures that are valid
    for the tub's current temperature range so the tub accepts them.
    """

    def test_set_temperature_change_is_reflected(self):
        """Set a temperature within the valid range; verify the tub accepts it."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            original = get_status(spa)
            orig_temp = original.set_temperature
            new_temp = _pick_alternate_temp(original)

            print(f"\n  Original set_temperature: {orig_temp}°, changing to {new_temp}°")
            print(f"  Range: {original.temperature_range.value}, Scale: {original.temperature_scale.value}")
            spa.set_temperature(new_temp)

            reported = _poll_for_temperature(spa, new_temp, timeout=5.0)

            # Restore
            spa.set_temperature(orig_temp)
            print(f"  Reported set_temperature: {reported}°  (restored to {orig_temp}°)")

        self.assertIsNotNone(reported)
        self.assertAlmostEqual(reported, new_temp, places=0)

    def test_set_temperature_restores(self):
        """Verify that after restoring, the tub returns to the original temp."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            original = get_status(spa)
            orig_temp = original.set_temperature
            alt = _pick_alternate_temp(original)

            spa.set_temperature(alt)
            _poll_for_temperature(spa, alt, timeout=5.0)

            spa.set_temperature(orig_temp)
            final_temp = _poll_for_temperature(spa, orig_temp, timeout=5.0)
            print(f"\n  alt={alt}°, restored to {orig_temp}°, final={final_temp}°")

        self.assertIsNotNone(final_temp)
        self.assertAlmostEqual(final_temp, orig_temp, places=0)


class TestLightControl(unittest.TestCase):
    """Toggle light1 and verify the state flips, then restore."""

    def test_toggle_light1(self):
        ip = get_spa_ip()
        with Client(ip) as spa:
            initial_status = get_status(spa)
            initial_light = initial_status.light1
            print(f"\n  Initial light1 state: {initial_light}")

            spa.toggle_light1()
            time.sleep(1.5)
            after_toggle = get_status(spa)
            print(f"  After toggle: {after_toggle.light1}")

            # Restore
            if after_toggle.light1 != initial_light:
                spa.toggle_light1()
                time.sleep(1.5)

        self.assertNotEqual(after_toggle.light1, initial_light)

    def test_set_light1(self):
        """set_light1() should bring light to desired state."""
        ip = get_spa_ip()
        with Client(ip) as spa:
            initial = get_status(spa)
            orig_light = initial.light1
            target = not orig_light

            spa.set_light1(target)
            time.sleep(1.5)
            after = get_status(spa)

            # Restore
            spa.set_light1(orig_light)
            time.sleep(1.5)

        self.assertEqual(after.light1, target)


class TestPumpControl(unittest.TestCase):
    """Toggle pump1 and verify, then restore.  Pump starts off (0)."""

    def test_toggle_pump1(self):
        ip = get_spa_ip()
        with Client(ip) as spa:
            initial = get_status(spa)
            initial_speed = initial.pump1
            print(f"\n  Initial pump1 speed: {initial_speed}")

            spa.toggle_pump1()
            time.sleep(1.5)
            after = get_status(spa)
            print(f"  After toggle: {after.pump1}")

            # Restore by toggling back the right number of times
            steps = (initial_speed - after.pump1) % 3
            for _ in range(steps):
                spa.toggle_pump1()
                time.sleep(0.3)
            time.sleep(1.2)

        self.assertEqual(after.pump1, (initial_speed + 1) % 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
