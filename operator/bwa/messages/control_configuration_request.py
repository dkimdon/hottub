"""ControlConfigurationRequest message (0x0a 0xbf 0x22).

The client sends this to request control configuration from the spa.
type=1 uses payload 0x02 0x00 0x00, type=2 uses 0x00 0x00 0x01.
"""

from ..message import Message


class ControlConfigurationRequest(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x22])
    MESSAGE_LENGTH = 3

    def __init__(self, request_type: int = 1) -> None:
        self.request_type = request_type

    def _parse(self, data: bytes) -> None:
        self.request_type = 1 if data == b"\x02\x00\x00" else 2

    def _serialize_payload(self) -> bytes:
        return b"\x02\x00\x00" if self.request_type == 1 else b"\x00\x00\x01"

    def __repr__(self) -> str:
        return f"<ControlConfigurationRequest type={self.request_type}>"
