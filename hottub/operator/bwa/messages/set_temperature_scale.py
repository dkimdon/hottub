"""SetTemperatureScale message (0x0a 0xbf 0x27).

Client → spa.  2-byte payload: [0x01, scale] where scale is 0x00=F, 0x01=C.
"""

from ..message import Message
from .status import TemperatureScale


class SetTemperatureScale(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x27])
    MESSAGE_LENGTH = 2

    def __init__(self, scale: TemperatureScale = TemperatureScale.FAHRENHEIT) -> None:
        self.scale = scale

    def _parse(self, data: bytes) -> None:
        self.scale = (
            TemperatureScale.CELSIUS if data[1] == 0x01 else TemperatureScale.FAHRENHEIT
        )

    def _serialize_payload(self) -> bytes:
        return bytes([0x01, 0x01 if self.scale == TemperatureScale.CELSIUS else 0x00])

    def __repr__(self) -> str:
        return f"<SetTemperatureScale {self.scale.value}>"
