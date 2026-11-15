"""FilterCycles message (0x0a 0xbf 0x23).

Sent by the spa in response to a filter-configuration request.
Payload is 8 bytes describing two filter cycle schedules.
"""

from ..message import Message


class FilterCycles(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x23])
    MESSAGE_LENGTH = 8

    def __init__(self) -> None:
        self.filter1_hour: int = 0
        self.filter1_minute: int = 0
        self.filter1_duration_hours: int = 0
        self.filter1_duration_minutes: int = 0
        self.filter2_enabled: bool = False
        self.filter2_hour: int = 0
        self.filter2_minute: int = 0
        self.filter2_duration_hours: int = 0
        self.filter2_duration_minutes: int = 0

    def _parse(self, data: bytes) -> None:
        self.filter1_hour = data[0]
        self.filter1_minute = data[1]
        self.filter1_duration_hours = data[2]
        self.filter1_duration_minutes = data[3]

        f2_hour_byte = data[4]
        self.filter2_enabled = bool(f2_hour_byte & 0x80)
        self.filter2_hour = f2_hour_byte & 0x7F
        self.filter2_minute = data[5]
        self.filter2_duration_hours = data[6]
        self.filter2_duration_minutes = data[7]

    def __repr__(self) -> str:
        f2_state = "enabled" if self.filter2_enabled else "disabled"
        return (
            f"<FilterCycles "
            f"filter1 {self.filter1_duration_hours}:{self.filter1_duration_minutes:02d}"
            f"@{self.filter1_hour:02d}:{self.filter1_minute:02d} "
            f"filter2({f2_state}) "
            f"{self.filter2_duration_hours}:{self.filter2_duration_minutes:02d}"
            f"@{self.filter2_hour:02d}:{self.filter2_minute:02d}>"
        )
