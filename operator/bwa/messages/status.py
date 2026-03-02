"""Status message — sent by the spa roughly once per second.

Payload layout (24 bytes, indices relative to the payload passed to _parse):
  [0]  unused
  [1]  F1 – flags: priming (0x01)
  [2]  CT – current temperature (0xFF = unknown; divide by 2 if Celsius)
  [3]  HH – hour (0–23 even in 12-h mode)
  [4]  MM – minute
  [5]  F2 – heating mode (bits 0-1: 0=ready, 1=rest, 2=ready_in_rest)
  [6–8] unused
  [9]  F3 – temp scale (0x01=Celsius), 24h clock (0x02)
  [10] F4 – heating active (0x30 != 0), temperature range (0x04=high)
  [11] PP – pump1 (bits 0–1), pump2 (bits 2–3)
  [12] unused
  [13] CP – circ pump (0x02)
  [14] LF – light1 (0x03 == on)
  [15–19] unused
  [20] ST – set temperature (divide by 2 if Celsius)
  [21–23] unused
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from ..message import Message


class HeatingMode(Enum):
    READY = "ready"
    REST = "rest"
    READY_IN_REST = "ready_in_rest"


class TemperatureScale(Enum):
    FAHRENHEIT = "fahrenheit"
    CELSIUS = "celsius"


class TemperatureRange(Enum):
    HIGH = "high"
    LOW = "low"


@dataclass
class Status(Message):
    MESSAGE_TYPE = bytes([0xFF, 0xAF, 0x13])
    MESSAGE_LENGTH = 24

    priming: bool = False
    heating_mode: HeatingMode = HeatingMode.READY
    temperature_scale: TemperatureScale = TemperatureScale.FAHRENHEIT
    twenty_four_hour_time: bool = False
    heating: bool = False
    temperature_range: TemperatureRange = TemperatureRange.HIGH
    hour: int = 0
    minute: int = 0
    circ_pump: bool = False
    pump1: int = 0   # 0=off, 1=low, 2=high
    pump2: int = 0
    light1: bool = False
    current_temperature: Optional[float] = None
    set_temperature: float = 100.0

    def _parse(self, data: bytes) -> None:
        self.priming = bool(data[1] & 0x01)

        hm = data[5] & 0x03
        self.heating_mode = {
            0: HeatingMode.READY,
            1: HeatingMode.REST,
            2: HeatingMode.READY_IN_REST,
        }.get(hm, HeatingMode.READY)

        f3 = data[9]
        self.temperature_scale = (
            TemperatureScale.CELSIUS if (f3 & 0x01) else TemperatureScale.FAHRENHEIT
        )
        self.twenty_four_hour_time = bool(f3 & 0x02)

        f4 = data[10]
        self.heating = bool(f4 & 0x30)
        self.temperature_range = (
            TemperatureRange.HIGH if (f4 & 0x04) else TemperatureRange.LOW
        )

        pp = data[11]
        self.pump1 = pp & 0x03
        self.pump2 = (pp >> 2) & 0x03

        self.circ_pump = bool(data[13] & 0x02)
        self.light1 = (data[14] & 0x03) == 0x03

        self.hour = data[3]
        self.minute = data[4]

        raw_current = data[2]
        self.current_temperature = None if raw_current == 0xFF else float(raw_current)

        raw_set = data[20]
        self.set_temperature = float(raw_set)

        if self.temperature_scale == TemperatureScale.CELSIUS:
            if self.current_temperature is not None:
                self.current_temperature /= 2.0
            self.set_temperature /= 2.0

    def format_time(self) -> str:
        if self.twenty_four_hour_time:
            return f"{self.hour:02d}:{self.minute:02d}"
        h = self.hour % 12 or 12
        suffix = "PM" if self.hour >= 12 else "AM"
        return f"{h}:{self.minute:02d}{suffix}"

    def __repr__(self) -> str:
        scale = "C" if self.temperature_scale == TemperatureScale.CELSIUS else "F"
        cur = (
            f"{self.current_temperature}"
            if self.current_temperature is not None
            else "--"
        )
        parts = [
            self.format_time(),
            f"{cur}/{self.set_temperature}°{scale}",
            self.heating_mode.value,
        ]
        if self.heating:
            parts.append("heating")
        parts.append(self.temperature_range.value)
        if self.circ_pump:
            parts.append("circ_pump")
        if self.pump1:
            parts.append(f"pump1={self.pump1}")
        if self.pump2:
            parts.append(f"pump2={self.pump2}")
        if self.light1:
            parts.append("light1")
        if self.priming:
            parts.append("priming")
        return f"<Status {' '.join(parts)}>"
