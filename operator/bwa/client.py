"""BWA TCP client — connects to a spa and sends/receives messages."""

import select
import socket
import time
from typing import Optional

from .message import Message, InvalidMessage
from . import messages as _msgs
from .messages.status import Status, TemperatureScale
from .messages.filter_cycles import FilterCycles
from .messages.set_temperature import SetTemperature
from .messages.toggle_item import ToggleItem


class Client:
    """TCP client that communicates with a Balboa spa over port 4257.

    The spa sends Status messages approximately once per second.
    Call poll() in a loop to process incoming messages.

    Example::

        spa = Client("192.168.1.50")
        spa.request_configuration()
        # wait for first status
        while spa.last_status is None:
            spa.poll()
        print(spa.last_status)
        spa.close()
    """

    DEFAULT_PORT = 4257

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((host, port))
        self._buf = b""
        self.last_status: Optional[Status] = None
        self.last_filter_cycles: Optional[FilterCycles] = None

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def poll(self) -> Message:
        """Block until one complete message arrives; return it.

        Side effects:
          - Updates self.last_status on Status messages.
          - Updates self.last_filter_cycles on FilterCycles messages.
        """
        frame = self._read_frame()
        msg = Message.parse(frame)
        if isinstance(msg, Status):
            self.last_status = msg
        elif isinstance(msg, FilterCycles):
            self.last_filter_cycles = msg
        return msg

    def poll_until_status(self, timeout: float = 5.0) -> Optional[Status]:
        """Poll until a Status message is received or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if not self._data_available(remaining):
                break
            try:
                msg = self.poll()
                if isinstance(msg, Status):
                    return msg
            except InvalidMessage:
                pass
        return self.last_status

    def messages_pending(self) -> bool:
        """Return True if there is data waiting to be read from the socket."""
        return self._data_available(0)

    def drain(self) -> None:
        """Consume and discard all currently pending messages."""
        while self.messages_pending():
            try:
                self.poll()
            except InvalidMessage:
                pass

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self, msg: Message) -> None:
        """Send a message to the spa."""
        self._sock.sendall(msg.to_bytes())

    def request_configuration(self) -> None:
        """Ask the spa to send its hardware configuration."""
        self.send(_msgs.ConfigurationRequest())

    def request_filter_configuration(self) -> None:
        """Ask the spa to send its filter cycle configuration."""
        self.send(_msgs.ControlConfigurationRequest(request_type=1))

    def request_control_info(self) -> None:
        """Ask the spa to send control configuration (type 2)."""
        self.send(_msgs.ControlConfigurationRequest(request_type=2))

    def set_temperature(self, desired: float) -> None:
        """Set the spa's target temperature.

        Pass degrees Fahrenheit (80–104 in high range, 50–80 in low range) or
        degrees Celsius (26–40 high, 10–26 low).  The library automatically
        handles the wire-level doubling required for Celsius.
        """
        wire_value = int(desired)
        if (
            self.last_status is not None
            and self.last_status.temperature_scale == TemperatureScale.CELSIUS
        ) or desired < 50:
            wire_value = int(desired * 2)
        msg = SetTemperature(wire_value)
        self.send(msg)

    def toggle_pump1(self) -> None:
        self.send(ToggleItem("pump1"))

    def toggle_pump2(self) -> None:
        self.send(ToggleItem("pump2"))

    def toggle_light1(self) -> None:
        self.send(ToggleItem("light1"))

    def toggle_heating_mode(self) -> None:
        self.send(ToggleItem("heating_mode"))

    def toggle_temperature_range(self) -> None:
        self.send(ToggleItem("temperature_range"))

    def set_pump1(self, desired: int) -> None:
        """Set pump1 to desired speed (0=off, 1=low, 2=high) by toggling."""
        if self.last_status is None:
            return
        current = self.last_status.pump1
        steps = (desired - current) % 3
        for _ in range(steps):
            self.toggle_pump1()
            time.sleep(0.1)

    def set_pump2(self, desired: int) -> None:
        """Set pump2 to desired speed (0=off, 1=low, 2=high) by toggling."""
        if self.last_status is None:
            return
        current = self.last_status.pump2
        steps = (desired - current) % 3
        for _ in range(steps):
            self.toggle_pump2()
            time.sleep(0.1)

    def set_light1(self, desired: bool) -> None:
        """Turn light1 on or off."""
        if self.last_status is None:
            return
        if self.last_status.light1 != desired:
            self.toggle_light1()

    def set_time(self, hour: int, minute: int, twenty_four_hour: bool = False) -> None:
        """Set the spa's clock."""
        self.send(_msgs.SetTime(hour, minute, twenty_four_hour))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _data_available(self, timeout: float) -> bool:
        ready, _, _ = select.select([self._sock], [], [], timeout)
        return bool(ready)

    def _read_frame(self) -> bytes:
        """Read bytes until we have a complete frame."""
        # Ensure we have at least the start byte + length byte
        while len(self._buf) < 2:
            self._buf += self._sock.recv(256)

        # If the first byte isn't 0x7e, scan forward to re-sync
        while self._buf and self._buf[0] != 0x7E:
            self._buf = self._buf[1:]
            while len(self._buf) < 2:
                self._buf += self._sock.recv(256)

        L = self._buf[1]
        total = L + 2  # start byte + L bytes (length..end_byte)

        while len(self._buf) < total:
            self._buf += self._sock.recv(256)

        frame = self._buf[:total]
        self._buf = self._buf[total:]
        return frame
