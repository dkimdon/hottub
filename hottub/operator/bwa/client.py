"""BWA TCP client — connects to a spa and sends/receives messages.

Every blocking operation has a deadline.  The spa's wifi module is known to
stop responding for long periods, so nothing here may wait forever:

  * connecting raises OSError (usually TimeoutError) after `timeout` seconds
  * poll() raises TimeoutError if no complete frame arrives in time
  * a connection closed by the spa raises ConnectionError
"""

import select
import socket
import time
from typing import Callable, Optional

from .message import Message, InvalidMessage, split_frames
from . import messages as _msgs
from .messages.status import Status, TemperatureScale
from .messages.filter_cycles import FilterCycles
from .messages.set_temperature import SetTemperature
from .messages.toggle_item import ToggleItem


class Client:
    """TCP client that communicates with a Balboa spa over port 4257.

    The spa sends Status messages approximately once per second.

    Example::

        with Client("192.168.1.50") as spa:
            status = spa.poll_until_status()
            if status is not None:
                print(status)
    """

    DEFAULT_PORT = 4257
    DEFAULT_TIMEOUT = 10.0

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""
        self._frames: list[bytes] = []
        self.last_status: Optional[Status] = None
        self.last_filter_cycles: Optional[FilterCycles] = None

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def poll(self, timeout: Optional[float] = None) -> Message:
        """Wait for one complete message and return it.

        Raises TimeoutError if none arrives within `timeout` seconds (default:
        the client's timeout), ConnectionError if the spa closes the
        connection, and InvalidMessage if the frame fails validation.

        Side effects: updates last_status / last_filter_cycles.
        """
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        msg = Message.parse(self._read_frame(deadline))
        if isinstance(msg, Status):
            self.last_status = msg
        elif isinstance(msg, FilterCycles):
            self.last_filter_cycles = msg
        return msg

    def poll_until_status(self, timeout: float = 5.0) -> Optional[Status]:
        """Return the next Status received, or None if none arrives in time.

        Never returns a previously received status: a non-None result was
        read from the spa during this call.
        """
        return self.wait_for_status(lambda _status: True, timeout)

    def wait_for_status(
        self, predicate: Callable[[Status], bool], timeout: float = 5.0
    ) -> Optional[Status]:
        """Return the first new Status satisfying `predicate`, else None."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                msg = self.poll(remaining)
            except TimeoutError:
                return None
            except InvalidMessage:
                continue
            if isinstance(msg, Status) and predicate(msg):
                return msg

    def messages_pending(self) -> bool:
        """Return True if a message can be read without waiting on the network."""
        if self._frames:
            return True
        ready, _, _ = select.select([self._sock], [], [], 0)
        return bool(ready)

    def drain(self) -> None:
        """Consume and discard all currently pending messages."""
        while self.messages_pending():
            try:
                self.poll(1.0)
            except (InvalidMessage, TimeoutError):
                pass

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self, msg: Message) -> None:
        """Send a message to the spa."""
        self._sock.settimeout(self.timeout)
        self._sock.sendall(msg.to_bytes())

    def request_configuration(self) -> None:
        """Ask the spa to send its hardware configuration."""
        self.send(_msgs.ConfigurationRequest())

    def request_filter_configuration(self) -> None:
        """Ask the spa to send its filter cycle configuration."""
        self.send(_msgs.ControlConfigurationRequest(_msgs.ControlConfigurationRequest.FILTER))

    def request_control_info(self) -> None:
        """Ask the spa to send its control configuration."""
        self.send(_msgs.ControlConfigurationRequest(_msgs.ControlConfigurationRequest.CONTROL))

    def set_temperature(self, desired: float) -> None:
        """Set the spa's target temperature.

        Pass degrees Fahrenheit or degrees Celsius to match the spa's current
        scale.  The spa only accepts values inside its current temperature
        range (see Status.temperature_range) and ignores anything else; the
        documented Fahrenheit limits are 50–80 (low) and 80–104 (high), though
        some models accept up to 106 in the high range.  The library handles
        the wire-level doubling required for Celsius.
        """
        wire_value = int(desired)
        if (
            self.last_status is not None
            and self.last_status.temperature_scale == TemperatureScale.CELSIUS
        ) or desired < 50:
            wire_value = int(desired * 2)
        if not 0 <= wire_value <= 0xFF:
            raise ValueError(f"Temperature out of range: {desired!r}")
        self.send(SetTemperature(wire_value))

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
        self._set_pump("pump1", desired)

    def set_pump2(self, desired: int) -> None:
        """Set pump2 to desired speed (0=off, 1=low, 2=high) by toggling."""
        self._set_pump("pump2", desired)

    def _set_pump(self, name: str, desired: int) -> None:
        if self.last_status is None:
            return
        steps = (desired - getattr(self.last_status, name)) % 3
        for _ in range(steps):
            self.send(ToggleItem(name))
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

    def _read_frame(self, deadline: float) -> bytes:
        """Return the next complete frame, reading from the socket as needed."""
        while not self._frames:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for a message from the spa")
            self._sock.settimeout(remaining)
            chunk = self._sock.recv(256)
            if not chunk:
                raise ConnectionError("Spa closed the connection")
            self._frames, self._buf = split_frames(self._buf + chunk)
        return self._frames.pop(0)
