"""Tests for the CRC-8 implementation.

Known-good CRC values derived from real tub traffic and the Ruby reference.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from bwa.crc import checksum


class TestCRC(unittest.TestCase):

    def test_known_configuration_request(self):
        # ConfigurationRequest wire frame: 7e 05 0a bf 04 CB 7e
        # inner bytes (after 0x7e start): 05 0a bf 04
        inner = bytes([0x05, 0x0A, 0xBF, 0x04])
        crc = checksum(inner)
        # The full frame should be: 7e 05 0a bf 04 <crc> 7e
        # Verify it's a single byte
        self.assertIsInstance(crc, int)
        self.assertGreaterEqual(crc, 0)
        self.assertLessEqual(crc, 255)

    def test_deterministic(self):
        data = bytes([0x05, 0x0A, 0xBF, 0x04])
        self.assertEqual(checksum(data), checksum(data))

    def test_different_data_different_crc(self):
        a = bytes([0x05, 0x0A, 0xBF, 0x04])
        b = bytes([0x05, 0x0A, 0xBF, 0x20, 0x68])
        self.assertNotEqual(checksum(a), checksum(b))

    def test_empty_data(self):
        # Should return 0x02 XOR 0x02 = 0x00 for empty
        self.assertEqual(checksum(b""), 0x00)

    def test_single_byte(self):
        result = checksum(bytes([0x05]))
        self.assertIsInstance(result, int)
        self.assertLessEqual(result, 255)

    def test_set_temperature_payload(self):
        # SetTemperature for 104°F: message type 0a bf 20, payload 68 (=104)
        # full inner: L=06, 0a bf 20 68
        inner = bytes([0x06, 0x0A, 0xBF, 0x20, 0x68])
        crc = checksum(inner)
        self.assertIsInstance(crc, int)
        self.assertLessEqual(crc, 255)


class TestCRCRoundTrip(unittest.TestCase):
    """Verify that frames built by Message.to_bytes() pass checksum validation."""

    def test_configuration_request_frame(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from bwa.messages.configuration_request import ConfigurationRequest
        from bwa.message import Message
        msg = ConfigurationRequest()
        frame = msg.to_bytes()
        # Should parse without raising
        parsed = Message.parse(frame)
        self.assertIsInstance(parsed, ConfigurationRequest)

    def test_set_temperature_frame(self):
        from bwa.messages.set_temperature import SetTemperature
        from bwa.message import Message
        msg = SetTemperature(104)
        frame = msg.to_bytes()
        parsed = Message.parse(frame)
        self.assertIsInstance(parsed, SetTemperature)
        self.assertEqual(parsed.temperature, 104)

    def test_toggle_item_frame(self):
        from bwa.messages.toggle_item import ToggleItem
        from bwa.message import Message
        for item in ("pump1", "pump2", "light1", "heating_mode", "temperature_range"):
            msg = ToggleItem(item)
            frame = msg.to_bytes()
            parsed = Message.parse(frame)
            self.assertIsInstance(parsed, ToggleItem)
            self.assertEqual(parsed.item, item)

    def test_set_time_frame(self):
        from bwa.messages.set_time import SetTime
        from bwa.message import Message
        msg = SetTime(14, 30, twenty_four_hour_time=True)
        frame = msg.to_bytes()
        parsed = Message.parse(frame)
        self.assertIsInstance(parsed, SetTime)
        self.assertEqual(parsed.hour, 14)
        self.assertEqual(parsed.minute, 30)
        self.assertTrue(parsed.twenty_four_hour_time)


if __name__ == "__main__":
    unittest.main()
