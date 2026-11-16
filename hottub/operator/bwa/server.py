"""Simulated BWA spa server for testing without real hardware.

Listens on a TCP port, accepts one client at a time, sends Status updates
(every second by default) and responds to requests the way a real spa does.
The `status` attribute is the simulated tub's state; tests may change it
directly to imitate someone pressing buttons on the front panel.
"""

import select
import socket
import time

from .message import Message, InvalidMessage, build_frame, split_frames
from . import messages as _msgs
from .messages.status import Status, TemperatureScale, HeatingMode, TemperatureRange
from .messages.control_configuration_request import ControlConfigurationRequest


class Server:
    """A simple simulated spa server.

    Usage::

        srv = Server(port=0)          # 0 = pick a free port; see srv.port
        threading.Thread(target=srv.run, daemon=True).start()
        # ... connect clients, then:
        srv.stop()
    """

    def __init__(self, port: int = 4257, status_interval: float = 1.0) -> None:
        self.status_interval = status_interval
        self.status = Status(set_temperature=102.0, current_temperature=100.0, heating=True)
        self._stop = False
        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_sock.bind(("127.0.0.1" if port == 0 else "", port))
        self._listen_sock.listen(1)
        self._listen_sock.settimeout(0.1)
        self.port = self._listen_sock.getsockname()[1]

    def run(self) -> None:
        """Accept connections and serve one at a time (blocking)."""
        try:
            while not self._stop:
                try:
                    client_sock, _addr = self._listen_sock.accept()
                except socket.timeout:
                    continue
                try:
                    self._serve_client(client_sock)
                except OSError:
                    pass
                finally:
                    client_sock.close()
        finally:
            self._listen_sock.close()

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _serve_client(self, sock: socket.socket) -> None:
        buf = b""
        last_status_time = float("-inf")

        while not self._stop:
            now = time.monotonic()
            if now - last_status_time >= self.status_interval:
                sock.sendall(self.status.to_bytes())
                last_status_time = now

            ready, _, _ = select.select([sock], [], [], min(0.05, self.status_interval))
            if not ready:
                continue

            chunk = sock.recv(256)
            if not chunk:
                break
            frames, buf = split_frames(buf + chunk)
            for frame in frames:
                try:
                    self._handle(sock, Message.parse(frame))
                except InvalidMessage:
                    pass

    def _handle(self, sock: socket.socket, msg: Message) -> None:
        if isinstance(msg, _msgs.ConfigurationRequest):
            sock.sendall(build_frame(_msgs.Configuration.MESSAGE_TYPE, bytes([
                0x02, 0x02, 0x80, 0x00, 0x15, 0x27, 0x10, 0xAB, 0xD2,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x15, 0x27, 0xFF, 0xFF, 0x10, 0xAB, 0xD2,
            ])))
        elif isinstance(msg, ControlConfigurationRequest):
            if msg.request == ControlConfigurationRequest.FILTER:
                sock.sendall(build_frame(_msgs.FilterCycles.MESSAGE_TYPE, bytes([
                    0x08, 0x00, 0x02, 0x00, 0x14, 0x00, 0x01, 0x00,
                ])))
            elif msg.request == ControlConfigurationRequest.CONTROL:
                sock.sendall(build_frame(_msgs.ControlConfiguration.MESSAGE_TYPE, bytes([
                    0x64, 0xDC, 0x11, 0x00, 0x42, 0x46, 0x42, 0x50, 0x32,
                    0x30, 0x20, 0x20, 0x01, 0x3D, 0x12, 0x38, 0x2E, 0x01,
                    0x0A, 0x04, 0x00,
                ])))
            else:
                sock.sendall(build_frame(_msgs.ControlConfiguration2.MESSAGE_TYPE, bytes([
                    0x0A, 0x00, 0x01, 0xD0, 0x00, 0x44,
                ])))
        elif isinstance(msg, _msgs.SetTemperature):
            temp = float(msg.temperature)
            if self.status.temperature_scale == TemperatureScale.CELSIUS:
                temp /= 2.0
            # Like a real spa, ignore temperatures outside the current range.
            if self._in_range(temp):
                self.status.set_temperature = temp
        elif isinstance(msg, _msgs.SetTemperatureScale):
            self.status.temperature_scale = msg.scale
        elif isinstance(msg, _msgs.ToggleItem):
            self._toggle(msg.item)

    def _in_range(self, temp: float) -> bool:
        if self.status.temperature_scale == TemperatureScale.CELSIUS:
            low, mid, high = 10, 26, 41
        else:
            low, mid, high = 50, 80, 106
        if self.status.temperature_range == TemperatureRange.HIGH:
            return mid <= temp <= high
        return low <= temp <= mid

    def _toggle(self, item: str) -> None:
        s = self.status
        if item == "heating_mode":
            s.heating_mode = (
                HeatingMode.READY if s.heating_mode == HeatingMode.REST else HeatingMode.REST
            )
        elif item == "temperature_range":
            # A real spa keeps a separate set temperature for each range.
            if s.temperature_range == TemperatureRange.LOW:
                s.temperature_range, s.set_temperature = TemperatureRange.HIGH, 100.0
            else:
                s.temperature_range, s.set_temperature = TemperatureRange.LOW, 60.0
        elif item == "pump1":
            s.pump1 = (s.pump1 + 1) % 3
        elif item == "pump2":
            s.pump2 = (s.pump2 + 1) % 3
        elif item == "light1":
            s.light1 = not s.light1
