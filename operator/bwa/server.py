"""Simulated BWA spa server for testing without real hardware.

Listens on TCP port 4257 (configurable), accepts one client at a time,
sends Status updates every second, and responds to configuration requests.
"""

import select
import socket
import time

from .message import Message, InvalidMessage
from . import messages as _msgs
from .messages.status import Status, TemperatureScale, HeatingMode, TemperatureRange
from .messages.set_temperature import SetTemperature
from .messages.set_temperature_scale import SetTemperatureScale
from .messages.toggle_item import ToggleItem


class Server:
    """A simple simulated spa server.

    Usage::

        import threading
        srv = Server(port=4257)
        t = threading.Thread(target=srv.run, daemon=True)
        t.start()
        # ... connect clients, then:
        srv.stop()
    """

    def __init__(self, port: int = 4257) -> None:
        self.port = port
        self._status = Status()
        self._status.set_temperature = 102.0
        self._status.current_temperature = 100.0
        self._status.heating = True
        self._stop = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Accept connections and serve one at a time (blocking)."""
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind(("", self.port))
        listen_sock.listen(1)
        listen_sock.settimeout(1.0)

        while not self._stop:
            try:
                client_sock, addr = listen_sock.accept()
            except socket.timeout:
                continue
            print(f"[Server] client connected from {addr}")
            try:
                self._serve_client(client_sock)
            finally:
                client_sock.close()

        listen_sock.close()

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _serve_client(self, sock: socket.socket) -> None:
        sock.setblocking(False)
        buf = b""
        last_status_time = 0.0

        while not self._stop:
            # Send a status update once per second
            now = time.monotonic()
            if now - last_status_time >= 1.0:
                self._send_status(sock)
                last_status_time = now

            # Check for incoming messages (100 ms window)
            ready, _, _ = select.select([sock], [], [], 0.1)
            if not ready:
                continue

            chunk = sock.recv(256)
            if not chunk:
                break
            buf += chunk

            # Parse all complete frames out of buf
            while len(buf) >= 2:
                if buf[0] != 0x7E:
                    buf = buf[1:]
                    continue
                L = buf[1]
                total = L + 2
                if len(buf) < total:
                    break
                frame = buf[:total]
                buf = buf[total:]
                try:
                    msg = Message.parse(frame)
                    self._handle(sock, msg)
                except InvalidMessage as e:
                    print(f"[Server] invalid message: {e}")

    def _handle(self, sock: socket.socket, msg: object) -> None:
        if isinstance(msg, _msgs.ConfigurationRequest):
            self._send_configuration(sock)
        elif isinstance(msg, _msgs.ControlConfigurationRequest):
            if msg.request_type == 1:
                self._send_control_configuration(sock)
            else:
                self._send_control_configuration2(sock)
        elif isinstance(msg, SetTemperature):
            temp = msg.temperature
            if self._status.temperature_scale == TemperatureScale.CELSIUS:
                temp /= 2.0
            self._status.set_temperature = float(temp)
        elif isinstance(msg, SetTemperatureScale):
            self._status.temperature_scale = msg.scale
        elif isinstance(msg, ToggleItem):
            self._toggle(msg.item)

    def _toggle(self, item: str) -> None:
        if item == "heating_mode":
            self._status.heating_mode = (
                HeatingMode.READY
                if self._status.heating_mode == HeatingMode.REST
                else HeatingMode.REST
            )
        elif item == "temperature_range":
            self._status.temperature_range = (
                TemperatureRange.HIGH
                if self._status.temperature_range == TemperatureRange.LOW
                else TemperatureRange.LOW
            )
        elif item == "pump1":
            self._status.pump1 = (self._status.pump1 + 1) % 3
        elif item == "pump2":
            self._status.pump2 = (self._status.pump2 + 1) % 3
        elif item == "light1":
            self._status.light1 = not self._status.light1

    def _send_status(self, sock: socket.socket) -> None:
        # Build status frame manually since Status is a dataclass, not a normal Message
        payload = _encode_status_payload(self._status)
        from .message import FRAME_START, FRAME_END
        from . import crc as _crc
        msg_type = Status.MESSAGE_TYPE
        L = len(payload) + 5
        inner = bytes([L]) + msg_type + payload
        checksum = _crc.checksum(inner)
        frame = bytes([FRAME_START]) + inner + bytes([checksum, FRAME_END])
        try:
            sock.sendall(frame)
        except OSError:
            pass

    def _send_raw(self, sock: socket.socket, msg_type_hex: bytes, payload: bytes) -> None:
        from .message import FRAME_START, FRAME_END
        from . import crc as _crc
        L = len(payload) + 5
        inner = bytes([L]) + msg_type_hex + payload
        checksum = _crc.checksum(inner)
        frame = bytes([FRAME_START]) + inner + bytes([checksum, FRAME_END])
        try:
            sock.sendall(frame)
        except OSError:
            pass

    def _send_configuration(self, sock: socket.socket) -> None:
        self._send_raw(
            sock,
            bytes([0x0A, 0xBF, 0x94]),
            bytes([
                0x02, 0x02, 0x80, 0x00, 0x15, 0x27, 0x10, 0xAB, 0xD2,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x15, 0x27, 0xFF, 0xFF, 0x10, 0xAB, 0xD2,
            ]),
        )

    def _send_control_configuration(self, sock: socket.socket) -> None:
        self._send_raw(
            sock,
            bytes([0x0A, 0xBF, 0x24]),
            bytes([
                0x64, 0xDC, 0x11, 0x00, 0x42, 0x46, 0x42, 0x50, 0x32,
                0x30, 0x20, 0x20, 0x01, 0x3D, 0x12, 0x38, 0x2E, 0x01,
                0x0A, 0x04, 0x00,
            ]),
        )

    def _send_control_configuration2(self, sock: socket.socket) -> None:
        self._send_raw(
            sock,
            bytes([0x0A, 0xBF, 0x2E]),
            bytes([0x0A, 0x00, 0x01, 0xD0, 0x00, 0x44]),
        )


def _encode_status_payload(s: Status) -> bytes:
    data = bytearray(24)

    data[1] = 0x01 if s.priming else 0x00

    hm_map = {
        HeatingMode.READY: 0x00,
        HeatingMode.REST: 0x01,
        HeatingMode.READY_IN_REST: 0x02,
    }
    data[5] = hm_map.get(s.heating_mode, 0x00)

    f3 = 0
    if s.temperature_scale == TemperatureScale.CELSIUS:
        f3 |= 0x01
    if s.twenty_four_hour_time:
        f3 |= 0x02
    data[9] = f3

    f4 = 0
    if s.heating:
        f4 |= 0x30
    if s.temperature_range == TemperatureRange.HIGH:
        f4 |= 0x04
    data[10] = f4

    data[11] = (s.pump1 & 0x03) | ((s.pump2 & 0x03) << 2)
    data[13] = 0x02 if s.circ_pump else 0x00
    data[14] = 0x03 if s.light1 else 0x00

    data[3] = s.hour
    data[4] = s.minute

    if s.temperature_scale == TemperatureScale.CELSIUS:
        data[2] = 0xFF if s.current_temperature is None else int(s.current_temperature * 2)
        data[20] = int(s.set_temperature * 2)
    else:
        data[2] = 0xFF if s.current_temperature is None else int(s.current_temperature)
        data[20] = int(s.set_temperature)

    return bytes(data)
