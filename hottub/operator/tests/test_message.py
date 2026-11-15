"""Unit tests for message parsing and serialisation using the simulated server."""

import sys
import os
import socket
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bwa.message import Message, InvalidMessage
from bwa.messages.status import Status, HeatingMode, TemperatureScale, TemperatureRange
from bwa.messages.configuration_request import ConfigurationRequest
from bwa.messages.set_temperature import SetTemperature
from bwa.messages.set_temperature_scale import SetTemperatureScale
from bwa.messages.set_time import SetTime
from bwa.messages.toggle_item import ToggleItem
from bwa.server import Server, _encode_status_payload
from bwa.client import Client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class ServerThread:
    """Context manager that runs a Server in a background thread."""

    def __init__(self, port: int) -> None:
        self.port = port
        self._server = Server(port=port)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self) -> "ServerThread":
        self._thread.start()
        time.sleep(0.05)  # give server time to bind
        return self

    def __exit__(self, *_) -> None:
        self._server.stop()


# ---------------------------------------------------------------------------
# CRC / framing tests (no network)
# ---------------------------------------------------------------------------

class TestFrameRoundTrip(unittest.TestCase):

    def _round_trip(self, msg: Message) -> Message:
        frame = msg.to_bytes()
        return Message.parse(frame)

    def test_configuration_request(self):
        parsed = self._round_trip(ConfigurationRequest())
        self.assertIsInstance(parsed, ConfigurationRequest)

    def test_set_temperature(self):
        for temp in (80, 102, 104):
            msg = SetTemperature(temp)
            parsed = self._round_trip(msg)
            self.assertIsInstance(parsed, SetTemperature)
            self.assertEqual(parsed.temperature, temp)

    def test_set_time_12h(self):
        msg = SetTime(9, 15, twenty_four_hour_time=False)
        parsed = self._round_trip(msg)
        self.assertIsInstance(parsed, SetTime)
        self.assertEqual(parsed.hour, 9)
        self.assertEqual(parsed.minute, 15)
        self.assertFalse(parsed.twenty_four_hour_time)

    def test_set_time_24h(self):
        msg = SetTime(21, 45, twenty_four_hour_time=True)
        parsed = self._round_trip(msg)
        self.assertTrue(parsed.twenty_four_hour_time)
        self.assertEqual(parsed.hour, 21)
        self.assertEqual(parsed.minute, 45)

    def test_toggle_items(self):
        for item in ("pump1", "pump2", "light1", "heating_mode", "temperature_range"):
            parsed = self._round_trip(ToggleItem(item))
            self.assertIsInstance(parsed, ToggleItem)
            self.assertEqual(parsed.item, item)

    def test_set_temperature_scale_fahrenheit(self):
        msg = SetTemperatureScale(TemperatureScale.FAHRENHEIT)
        parsed = self._round_trip(msg)
        self.assertIsInstance(parsed, SetTemperatureScale)
        self.assertEqual(parsed.scale, TemperatureScale.FAHRENHEIT)

    def test_set_temperature_scale_celsius(self):
        msg = SetTemperatureScale(TemperatureScale.CELSIUS)
        parsed = self._round_trip(msg)
        self.assertEqual(parsed.scale, TemperatureScale.CELSIUS)

    def test_invalid_crc_raises(self):
        msg = ConfigurationRequest()
        frame = bytearray(msg.to_bytes())
        frame[-2] ^= 0xFF  # corrupt CRC
        with self.assertRaises(InvalidMessage):
            Message.parse(bytes(frame))

    def test_invalid_start_byte_raises(self):
        msg = ConfigurationRequest()
        frame = bytearray(msg.to_bytes())
        frame[0] = 0x00
        with self.assertRaises(InvalidMessage):
            Message.parse(bytes(frame))

    def test_unknown_message_type_raises(self):
        # Build a frame with a valid CRC but an unknown message type
        from bwa import crc as _crc
        payload = b""
        msg_type = bytes([0xDE, 0xAD, 0xBE])
        L = len(payload) + 5
        inner = bytes([L]) + msg_type + payload
        checksum = _crc.checksum(inner)
        frame = bytes([0x7E]) + inner + bytes([checksum, 0x7E])
        with self.assertRaises(InvalidMessage):
            Message.parse(frame)


# ---------------------------------------------------------------------------
# Status payload encoding / decoding
# ---------------------------------------------------------------------------

class TestStatusEncoding(unittest.TestCase):

    def _make_status_frame(self, s: Status) -> bytes:
        """Build a complete Status wire frame from a Status object."""
        from bwa import crc as _crc
        payload = _encode_status_payload(s)
        L = len(payload) + 5
        inner = bytes([L]) + Status.MESSAGE_TYPE + payload
        checksum = _crc.checksum(inner)
        return bytes([0x7E]) + inner + bytes([checksum, 0x7E])

    def _round_trip(self, s: Status) -> Status:
        frame = self._make_status_frame(s)
        return Message.parse(frame)

    def test_current_temperature_fahrenheit(self):
        s = Status()
        s.current_temperature = 103.0
        s.set_temperature = 104.0
        s.temperature_scale = TemperatureScale.FAHRENHEIT
        parsed = self._round_trip(s)
        self.assertEqual(parsed.current_temperature, 103.0)
        self.assertEqual(parsed.set_temperature, 104.0)
        self.assertEqual(parsed.temperature_scale, TemperatureScale.FAHRENHEIT)

    def test_current_temperature_none(self):
        s = Status()
        s.current_temperature = None
        parsed = self._round_trip(s)
        self.assertIsNone(parsed.current_temperature)

    def test_celsius_temperature(self):
        s = Status()
        s.temperature_scale = TemperatureScale.CELSIUS
        s.current_temperature = 38.5
        s.set_temperature = 40.0
        parsed = self._round_trip(s)
        self.assertEqual(parsed.temperature_scale, TemperatureScale.CELSIUS)
        self.assertAlmostEqual(parsed.current_temperature, 38.5, places=1)
        self.assertAlmostEqual(parsed.set_temperature, 40.0, places=1)

    def test_heating_mode_rest(self):
        s = Status()
        s.heating_mode = HeatingMode.REST
        parsed = self._round_trip(s)
        self.assertEqual(parsed.heating_mode, HeatingMode.REST)

    def test_heating_mode_ready_in_rest(self):
        s = Status()
        s.heating_mode = HeatingMode.READY_IN_REST
        parsed = self._round_trip(s)
        self.assertEqual(parsed.heating_mode, HeatingMode.READY_IN_REST)

    def test_pump_states(self):
        s = Status()
        s.pump1 = 2
        s.pump2 = 1
        parsed = self._round_trip(s)
        self.assertEqual(parsed.pump1, 2)
        self.assertEqual(parsed.pump2, 1)

    def test_lights_and_circ_pump(self):
        s = Status()
        s.light1 = True
        s.circ_pump = True
        parsed = self._round_trip(s)
        self.assertTrue(parsed.light1)
        self.assertTrue(parsed.circ_pump)

    def test_priming_flag(self):
        s = Status()
        s.priming = True
        parsed = self._round_trip(s)
        self.assertTrue(parsed.priming)

    def test_24h_time(self):
        s = Status()
        s.hour = 23
        s.minute = 59
        s.twenty_four_hour_time = True
        parsed = self._round_trip(s)
        self.assertEqual(parsed.hour, 23)
        self.assertEqual(parsed.minute, 59)
        self.assertTrue(parsed.twenty_four_hour_time)

    def test_temperature_range_low(self):
        s = Status()
        s.temperature_range = TemperatureRange.LOW
        parsed = self._round_trip(s)
        self.assertEqual(parsed.temperature_range, TemperatureRange.LOW)


# ---------------------------------------------------------------------------
# Integration tests using the simulated server
# ---------------------------------------------------------------------------

class TestClientServer(unittest.TestCase):

    def setUp(self):
        self.port = find_free_port()
        self._srv_ctx = ServerThread(self.port)
        self._srv_ctx.__enter__()

    def tearDown(self):
        self._srv_ctx.__exit__()

    def test_poll_receives_status(self):
        with Client("127.0.0.1", self.port) as spa:
            status = spa.poll_until_status(timeout=3.0)
        self.assertIsNotNone(status)
        self.assertIsInstance(status, Status)

    def test_set_temperature_reflected(self):
        with Client("127.0.0.1", self.port) as spa:
            spa.poll_until_status(timeout=3.0)
            spa.set_temperature(104)
            # Wait for the server to update and send a new status
            time.sleep(1.2)
            status = spa.poll_until_status(timeout=3.0)
        self.assertIsNotNone(status)
        self.assertEqual(status.set_temperature, 104.0)

    def test_toggle_light1(self):
        with Client("127.0.0.1", self.port) as spa:
            s0 = spa.poll_until_status(timeout=3.0)
            initial = s0.light1
            spa.toggle_light1()
            time.sleep(1.2)
            s1 = spa.poll_until_status(timeout=3.0)
        self.assertIsNotNone(s1)
        self.assertNotEqual(s1.light1, initial)

    def test_toggle_pump1_cycles(self):
        with Client("127.0.0.1", self.port) as spa:
            s0 = spa.poll_until_status(timeout=3.0)
            initial = s0.pump1  # starts at 0
            spa.toggle_pump1()
            time.sleep(1.2)
            s1 = spa.poll_until_status(timeout=3.0)
        self.assertEqual(s1.pump1, (initial + 1) % 3)

    def test_request_configuration_no_crash(self):
        with Client("127.0.0.1", self.port) as spa:
            spa.request_configuration()
            # drain responses
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if spa.messages_pending():
                    spa.poll()
                else:
                    time.sleep(0.05)

    def test_messages_pending(self):
        with Client("127.0.0.1", self.port) as spa:
            # The server sends status every second; after 1.5s something should be pending
            time.sleep(1.5)
            self.assertTrue(spa.messages_pending())

    def test_context_manager(self):
        with Client("127.0.0.1", self.port) as spa:
            status = spa.poll_until_status(timeout=3.0)
            self.assertIsNotNone(status)
        # socket should be closed after __exit__; further operations raise
        with self.assertRaises(OSError):
            spa.poll()


if __name__ == "__main__":
    unittest.main(verbosity=2)
