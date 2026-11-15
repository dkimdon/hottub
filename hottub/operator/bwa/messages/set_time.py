"""SetTime message (0x0a 0xbf 0x21).

Client → spa.  2-byte payload: [hour_byte, minute].
The high bit of hour_byte enables 24-hour display mode.
"""

from ..message import Message


class SetTime(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x21])
    MESSAGE_LENGTH = 2

    def __init__(
        self,
        hour: int = 0,
        minute: int = 0,
        twenty_four_hour_time: bool = False,
    ) -> None:
        self.hour = hour
        self.minute = minute
        self.twenty_four_hour_time = twenty_four_hour_time

    def _parse(self, data: bytes) -> None:
        self.hour = data[0] & 0x7F
        self.minute = data[1]
        self.twenty_four_hour_time = bool(data[0] & 0x80)

    def _serialize_payload(self) -> bytes:
        hour_byte = self.hour | (0x80 if self.twenty_four_hour_time else 0x00)
        return bytes([hour_byte, self.minute])

    def __repr__(self) -> str:
        if self.twenty_four_hour_time:
            time_str = f"{self.hour:02d}:{self.minute:02d}"
        else:
            h = self.hour % 12 or 12
            suffix = "PM" if self.hour >= 12 else "AM"
            time_str = f"{h}:{self.minute:02d}{suffix}"
        return f"<SetTime {time_str}>"
