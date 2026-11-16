"""Unit tests for message framing, parsing and the client, using the simulated server."""

import socket
import threading
import time
import unittest

from support import ServerThread

from bwa.client import Client
from bwa.message import Message, InvalidMessage, build_frame, split_frames
from bwa.messages import (
    ConfigurationRequest,
    ControlConfigurationRequest,
    FilterCycles,
    SetTemperature,
    SetTemperatureScale,
    SetTime,
    ToggleItem,
)
from bwa.messages.status import Status, HeatingMode, TemperatureScale, TemperatureRange


def round_trip(msg: Message) -> Message:
    return Message.parse(msg.to_bytes())


class TestFrameRoundTrip(unittest.TestCase):

    def test_configuration_request(self):
        self.assertIsInstance(round_trip(ConfigurationRequest()), ConfigurationRequest)

    def test_set_temperature(self):
        for temp in (50, 80, 102, 104, 106):
            parsed = round_trip(SetTemperature(temp))
            self.assertIsInstance(parsed, SetTemperature)
            self.assertEqual(parsed.temperature, temp)

    def test_set_temperature_wire_bytes(self):
        frame = SetTemperature(104).to_bytes()
        self.assertEqual(frame[:6], bytes.fromhex("7e060abf2068"))

    def test_set_time(self):
        parsed = round_trip(SetTime(9, 15, twenty_four_hour_time=False))
        self.assertEqual((parsed.hour, parsed.minute, parsed.twenty_four_hour_time), (9, 15, False))
        parsed = round_trip(SetTime(21, 45, twenty_four_hour_time=True))
        self.assertEqual((parsed.hour, parsed.minute, parsed.twenty_four_hour_time), (21, 45, True))

    def test_toggle_items(self):
        for item in ("pump1", "pump2", "light1", "heating_mode", "temperature_range"):
            parsed = round_trip(ToggleItem(item))
            self.assertIsInstance(parsed, ToggleItem)
            self.assertEqual(parsed.item, item)

    def test_toggle_wire_bytes(self):
        self.assertEqual(ToggleItem("heating_mode").to_bytes()[2:7], bytes.fromhex("0abf115100"))
        self.assertEqual(ToggleItem("temperature_range").to_bytes()[2:7], bytes.fromhex("0abf115000"))

    def test_set_temperature_scale(self):
        for scale in TemperatureScale:
            self.assertEqual(round_trip(SetTemperatureScale(scale)).scale, scale)

    def test_control_configuration_request_payloads(self):
        # Payloads from doc/protocol.md in the Ruby repository.
        cases = {
            ControlConfigurationRequest.FILTER: "010000",
            ControlConfigurationRequest.CONTROL: "020000",
            ControlConfigurationRequest.CONTROL2: "000001",
        }
        for request, payload in cases.items():
            frame = ControlConfigurationRequest(request).to_bytes()
            self.assertEqual(frame[2:8], bytes.fromhex("0abf22" + payload))
            self.assertEqual(Message.parse(frame).request, request)

    def test_invalid_crc_raises(self):
        frame = bytearray(ConfigurationRequest().to_bytes())
        frame[-2] ^= 0xFF
        with self.assertRaises(InvalidMessage):
            Message.parse(bytes(frame))

    def test_invalid_start_byte_raises(self):
        frame = bytearray(ConfigurationRequest().to_bytes())
        frame[0] = 0x00
        with self.assertRaises(InvalidMessage):
            Message.parse(bytes(frame))

    def test_short_frame_raises(self):
        for frame in (b"", b"\x7e", b"\x7e\x7e", b"\x7e\x00\x7e"):
            with self.assertRaises(InvalidMessage):
                Message.parse(frame)

    def test_unknown_message_type_raises(self):
        with self.assertRaises(InvalidMessage):
            Message.parse(build_frame(bytes([0xDE, 0xAD, 0xBE])))


class TestSplitFrames(unittest.TestCase):

    def test_splits_multiple_frames_and_keeps_tail(self):
        a = ConfigurationRequest().to_bytes()
        b = SetTemperature(104).to_bytes()
        frames, tail = split_frames(a + b + b[:3])
        self.assertEqual(frames, [a, b])
        self.assertEqual(tail, b[:3])

    def test_skips_leading_garbage(self):
        a = ConfigurationRequest().to_bytes()
        frames, tail = split_frames(b"\x01\x02\x03" + a)
        self.assertEqual(frames, [a])
        self.assertEqual(tail, b"")

    def test_resyncs_after_truncated_frame(self):
        # The tail of a frame whose start was lost, then a good frame.  The
        # stray end delimiter must not be taken for a frame start.
        a = ConfigurationRequest().to_bytes()
        b = SetTemperature(104).to_bytes()
        frames, _ = split_frames(a[3:] + b)
        self.assertEqual(frames, [b])


class TestStatusEncoding(unittest.TestCase):

    def test_fahrenheit(self):
        parsed = round_trip(Status(current_temperature=103.0, set_temperature=106.0))
        self.assertEqual(parsed.current_temperature, 103.0)
        self.assertEqual(parsed.set_temperature, 106.0)
        self.assertEqual(parsed.temperature_scale, TemperatureScale.FAHRENHEIT)

    def test_current_temperature_unknown(self):
        self.assertIsNone(round_trip(Status(current_temperature=None)).current_temperature)

    def test_celsius(self):
        parsed = round_trip(Status(
            temperature_scale=TemperatureScale.CELSIUS,
            current_temperature=38.5,
            set_temperature=40.0,
        ))
        self.assertEqual(parsed.temperature_scale, TemperatureScale.CELSIUS)
        self.assertEqual(parsed.current_temperature, 38.5)
        self.assertEqual(parsed.set_temperature, 40.0)

    def test_all_fields_round_trip(self):
        original = Status(
            priming=True,
            heating_mode=HeatingMode.READY_IN_REST,
            twenty_four_hour_time=True,
            heating=True,
            temperature_range=TemperatureRange.LOW,
            hour=23,
            minute=59,
            circ_pump=True,
            pump1=2,
            pump2=1,
            light1=True,
            current_temperature=77.0,
            set_temperature=60.0,
        )
        self.assertEqual(round_trip(original), original)

    def test_payload_byte_positions(self):
        # Positions from doc/protocol.md: current temp at 2, set temp at 20,
        # heating mode at 5, range flag 0x04 at 10.
        payload = Status(
            current_temperature=99.0,
            set_temperature=104.0,
            heating_mode=HeatingMode.REST,
            temperature_range=TemperatureRange.HIGH,
        )._serialize_payload()
        self.assertEqual(len(payload), 24)
        self.assertEqual(payload[2], 99)
        self.assertEqual(payload[20], 104)
        self.assertEqual(payload[5], 0x01)
        self.assertEqual(payload[10] & 0x04, 0x04)


class TestClientServer(unittest.TestCase):

    def setUp(self):
        self.srv = ServerThread()
        self.srv.__enter__()
        self.addCleanup(self.srv.__exit__)

    def client(self) -> Client:
        return Client("127.0.0.1", self.srv.port, timeout=2.0)

    def test_poll_receives_status(self):
        with self.client() as spa:
            status = spa.poll_until_status(timeout=2.0)
        self.assertIsInstance(status, Status)

    def test_set_temperature_reflected(self):
        with self.client() as spa:
            spa.set_temperature(104)
            status = spa.wait_for_status(lambda s: s.set_temperature == 104.0, timeout=2.0)
        self.assertIsNotNone(status)

    def test_set_temperature_106(self):
        with self.client() as spa:
            spa.set_temperature(106)
            status = spa.wait_for_status(lambda s: s.set_temperature == 106.0, timeout=2.0)
        self.assertIsNotNone(status)

    def test_toggles(self):
        with self.client() as spa:
            spa.toggle_light1()
            self.assertIsNotNone(spa.wait_for_status(lambda s: s.light1, timeout=2.0))
            spa.toggle_pump1()
            self.assertIsNotNone(spa.wait_for_status(lambda s: s.pump1 == 1, timeout=2.0))
            spa.toggle_heating_mode()
            self.assertIsNotNone(
                spa.wait_for_status(lambda s: s.heating_mode == HeatingMode.REST, timeout=2.0)
            )
            spa.toggle_temperature_range()
            self.assertIsNotNone(
                spa.wait_for_status(
                    lambda s: s.temperature_range == TemperatureRange.LOW, timeout=2.0
                )
            )

    def test_filter_configuration_request(self):
        with self.client() as spa:
            spa.request_filter_configuration()
            deadline = time.monotonic() + 2.0
            while spa.last_filter_cycles is None and time.monotonic() < deadline:
                spa.poll(1.0)
        self.assertIsInstance(spa.last_filter_cycles, FilterCycles)

    def test_messages_pending(self):
        with self.client() as spa:
            time.sleep(0.2)
            self.assertTrue(spa.messages_pending())

    def test_poll_after_close_raises(self):
        with self.client() as spa:
            spa.poll_until_status(timeout=2.0)
        with self.assertRaises(OSError):
            spa.poll(0.5)


class TestClientFailures(unittest.TestCase):
    """The failure modes that matter when the spa's wifi module misbehaves."""

    def _listener(self, behaviour):
        listen = socket.socket()
        listen.bind(("127.0.0.1", 0))
        listen.listen(1)
        self.addCleanup(listen.close)

        def serve():
            try:
                conn, _ = listen.accept()
            except OSError:
                return
            with conn:
                behaviour(conn)

        threading.Thread(target=serve, daemon=True).start()
        return listen.getsockname()[1]

    def test_closed_connection_raises_instead_of_spinning(self):
        port = self._listener(lambda conn: None)  # accept, then close at once
        with Client("127.0.0.1", port, timeout=2.0) as spa:
            started = time.monotonic()
            with self.assertRaises(ConnectionError):
                spa.poll()
            self.assertLess(time.monotonic() - started, 1.5)

    def test_silent_spa_times_out(self):
        port = self._listener(lambda conn: time.sleep(1.0))
        with Client("127.0.0.1", port, timeout=2.0) as spa:
            with self.assertRaises(TimeoutError):
                spa.poll(0.2)
            self.assertIsNone(spa.poll_until_status(timeout=0.2))

    def test_partial_frame_times_out(self):
        def behaviour(conn):
            conn.sendall(Status().to_bytes()[:10])
            time.sleep(1.0)

        port = self._listener(behaviour)
        with Client("127.0.0.1", port, timeout=2.0) as spa:
            started = time.monotonic()
            self.assertIsNone(spa.poll_until_status(timeout=0.3))
            self.assertLess(time.monotonic() - started, 0.9)

    def test_no_stale_status_after_spa_goes_quiet(self):
        def behaviour(conn):
            conn.sendall(Status().to_bytes())
            time.sleep(1.0)

        port = self._listener(behaviour)
        with Client("127.0.0.1", port, timeout=2.0) as spa:
            self.assertIsNotNone(spa.poll_until_status(timeout=0.5))
            self.assertIsNone(spa.poll_until_status(timeout=0.2))

    def test_resyncs_after_garbage(self):
        # Garbage that looks like a frame header swallows the frame behind it;
        # the client must recover on the frames that follow.
        def behaviour(conn):
            conn.sendall(b"\x00\x7e\x7e\x13garbage" + Status(set_temperature=103.0).to_bytes() * 3)
            time.sleep(0.5)

        port = self._listener(behaviour)
        with Client("127.0.0.1", port, timeout=2.0) as spa:
            status = spa.poll_until_status(timeout=1.0)
        self.assertIsNotNone(status)
        self.assertEqual(status.set_temperature, 103.0)

    def test_connect_refused_raises_oserror(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(OSError):
            Client("127.0.0.1", port, timeout=1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
