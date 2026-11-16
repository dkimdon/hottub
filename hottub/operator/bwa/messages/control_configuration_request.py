"""ControlConfigurationRequest message (0x0a 0xbf 0x22).

Client → spa.  The 3-byte payload selects what is being requested:

  01 00 00   filter cycle configuration   (answered with FilterCycles)
  02 00 00   control configuration        (answered with ControlConfiguration)
  00 00 01   control configuration, part 2 (answered with ControlConfiguration2)
"""

from ..message import Message


class ControlConfigurationRequest(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x22])
    MESSAGE_LENGTH = 3

    FILTER = b"\x01\x00\x00"
    CONTROL = b"\x02\x00\x00"
    CONTROL2 = b"\x00\x00\x01"

    def __init__(self, request: bytes = CONTROL) -> None:
        if len(request) != self.MESSAGE_LENGTH:
            raise ValueError("request must be 3 bytes")
        self.request = request

    def _parse(self, data: bytes) -> None:
        self.request = data

    def _serialize_payload(self) -> bytes:
        return self.request

    def __repr__(self) -> str:
        return f"<ControlConfigurationRequest {self.request.hex(' ')}>"
