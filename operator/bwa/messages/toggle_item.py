"""ToggleItem message (0x0a 0xbf 0x11).

Client → spa.  2-byte payload: [item_code, 0x00].
Each call cycles the named item one step forward.
"""

from enum import Enum
from ..message import Message


class ToggleItem(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x11])
    MESSAGE_LENGTH = 2

    _CODE_TO_ITEM = {
        0x04: "pump1",
        0x05: "pump2",
        0x11: "light1",
        0x50: "temperature_range",
        0x51: "heating_mode",
    }
    _ITEM_TO_CODE = {v: k for k, v in _CODE_TO_ITEM.items()}

    def __init__(self, item: str = "") -> None:
        self.item = item

    def _parse(self, data: bytes) -> None:
        self.item = self._CODE_TO_ITEM.get(data[0], f"unknown(0x{data[0]:02x})")

    def _serialize_payload(self) -> bytes:
        code = self._ITEM_TO_CODE.get(self.item)
        if code is None:
            raise ValueError(f"Unknown toggle item: {self.item!r}")
        return bytes([code, 0x00])

    def __repr__(self) -> str:
        return f"<ToggleItem {self.item}>"
