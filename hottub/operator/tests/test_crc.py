"""Tests for the CRC-8 implementation and frame building."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bwa.crc import checksum
from bwa.message import build_frame


class TestCRC(unittest.TestCase):

    def test_empty_data(self):
        # init 0x02 XOR final mask 0x02
        self.assertEqual(checksum(b""), 0x00)

    def test_configuration_request_known_answer(self):
        # The configuration request is the well-known frame 7e 05 0a bf 04 77 7e.
        self.assertEqual(checksum(bytes.fromhex("050abf04")), 0x77)

    def test_build_frame_known_answer(self):
        self.assertEqual(
            build_frame(bytes.fromhex("0abf04")), bytes.fromhex("7e050abf04777e")
        )

    def test_single_bit_change_changes_crc(self):
        base = bytes.fromhex("060abf2068")  # set temperature 104
        for i in range(len(base) * 8):
            flipped = bytearray(base)
            flipped[i // 8] ^= 1 << (i % 8)
            self.assertNotEqual(checksum(bytes(flipped)), checksum(base))


if __name__ == "__main__":
    unittest.main()
