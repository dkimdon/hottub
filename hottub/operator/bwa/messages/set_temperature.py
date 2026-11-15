"""SetTemperature message (0x0a 0xbf 0x20).

Client → spa.  Single-byte payload: the target temperature.
If the spa is in Celsius mode, the value must be pre-doubled (e.g. 38°C → 76).
Use Client.set_temperature() which handles the doubling automatically.
"""

from ..message import Message


class SetTemperature(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x20])
    MESSAGE_LENGTH = 1

    def __init__(self, temperature: int = 0) -> None:
        # temperature here is the raw wire value (pre-doubled for Celsius)
        self.temperature = temperature

    def _parse(self, data: bytes) -> None:
        self.temperature = data[0]

    def _serialize_payload(self) -> bytes:
        return bytes([self.temperature & 0xFF])

    def __repr__(self) -> str:
        return f"<SetTemperature {self.temperature}>"
