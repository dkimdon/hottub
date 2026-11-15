"""Control configuration response messages.

ControlConfiguration  (0x0a 0xbf 0x24) – 21-byte payload
ControlConfiguration2 (0x0a 0xbf 0x2e) –  6-byte payload
"""

from ..message import Message


class ControlConfiguration(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x24])
    MESSAGE_LENGTH = 21

    def __init__(self) -> None:
        self.raw_payload: bytes = b""

    def _parse(self, data: bytes) -> None:
        self.raw_payload = data

    def __repr__(self) -> str:
        return f"<ControlConfiguration {self.raw_payload.hex(' ')}>"


class ControlConfiguration2(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x2E])
    MESSAGE_LENGTH = 6

    def __init__(self) -> None:
        self.raw_payload: bytes = b""

    def _parse(self, data: bytes) -> None:
        self.raw_payload = data

    def __repr__(self) -> str:
        return f"<ControlConfiguration2 {self.raw_payload.hex(' ')}>"
