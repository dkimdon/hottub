"""Configuration response message (0x0a 0xbf 0x94).

Sent by the spa in response to a ConfigurationRequest.
Payload is 25 bytes; we expose the raw bytes for inspection.
"""

from ..message import Message


class Configuration(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x94])
    MESSAGE_LENGTH = 25

    def __init__(self) -> None:
        self.raw_payload: bytes = b""

    def _parse(self, data: bytes) -> None:
        self.raw_payload = data

    def __repr__(self) -> str:
        return f"<Configuration {self.raw_payload.hex(' ')}>"
