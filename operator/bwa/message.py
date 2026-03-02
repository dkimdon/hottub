"""Base Message class implementing the BWA binary wire protocol framing.

Wire format for every message:
  [0x7e] [L] [T0 T1 T2] [payload...] [CRC] [0x7e]

Where:
  L   = len(payload) + 5  (covers the length byte itself, 3-byte type, payload)
  CRC = BWA CRC-8 over bytes [L T0 T1 T2 payload...]
  Total frame length = L + 2
"""

from __future__ import annotations
from typing import ClassVar
from . import crc as _crc

FRAME_START = FRAME_END = 0x7E


class InvalidMessage(Exception):
    def __init__(self, reason: str, raw: bytes):
        super().__init__(reason)
        self.raw = raw


class Message:
    """Base class for all BWA messages."""

    MESSAGE_TYPE: ClassVar[bytes]   # 3-byte type identifier
    MESSAGE_LENGTH: ClassVar[int]   # expected payload byte count

    # Registry populated by __init_subclass__
    _registry: ClassVar[dict[bytes, type[Message]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "MESSAGE_TYPE"):
            Message._registry[cls.MESSAGE_TYPE] = cls

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, frame: bytes) -> "Message":
        """Parse a complete wire frame and return the appropriate Message subclass."""
        if len(frame) < 2:
            raise InvalidMessage("Frame too short", frame)
        if frame[0] != FRAME_START or frame[-1] != FRAME_END:
            raise InvalidMessage("Missing frame delimiters", frame)

        L = frame[1]
        if len(frame) - 2 != L:
            raise InvalidMessage(
                f"Incorrect frame length (got {len(frame) - 2}, expected {L})", frame
            )

        expected_crc = _crc.checksum(frame[1:-2])
        if expected_crc != frame[-2]:
            raise InvalidMessage(
                f"CRC mismatch (got {frame[-2]:#04x}, expected {expected_crc:#04x})",
                frame,
            )

        msg_type = bytes(frame[2:5])
        subcls = cls._registry.get(msg_type)
        if subcls is None:
            raise InvalidMessage(
                f"Unknown message type {msg_type.hex()}", frame
            )

        payload = bytes(frame[5:-2])
        if len(payload) != subcls.MESSAGE_LENGTH:
            raise InvalidMessage(
                f"Wrong payload length for {subcls.__name__} "
                f"(got {len(payload)}, expected {subcls.MESSAGE_LENGTH})",
                frame,
            )

        obj = subcls.__new__(subcls)
        obj._raw = frame
        obj._parse(payload)
        return obj

    def _parse(self, payload: bytes) -> None:
        """Subclasses override to decode the payload bytes."""

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _serialize_payload(self) -> bytes:
        """Subclasses override to encode to payload bytes."""
        return b""

    def to_bytes(self) -> bytes:
        """Encode this message to a complete wire frame."""
        payload = self._serialize_payload()
        L = len(payload) + 5
        inner = bytes([L]) + self.MESSAGE_TYPE + payload
        checksum = _crc.checksum(inner)
        return bytes([FRAME_START]) + inner + bytes([checksum, FRAME_END])

    # ------------------------------------------------------------------
    # Stream reading helper
    # ------------------------------------------------------------------

    @staticmethod
    def read_frame(sock) -> bytes:
        """Read exactly one complete BWA frame from a socket.

        Blocks until a full frame is available.  Raises InvalidMessage if
        the sync byte is wrong or the socket closes mid-frame.
        """
        # Read start delimiter + length byte
        header = _recv_exactly(sock, 2)
        if not header:
            raise ConnectionError("Socket closed")
        if header[0] != FRAME_START:
            raise InvalidMessage(f"Expected frame start 0x7e, got {header[0]:#04x}", header)
        L = header[1]
        # Read remaining L bytes (type + payload + crc + end delimiter)
        rest = _recv_exactly(sock, L)
        if not rest:
            raise ConnectionError("Socket closed mid-frame")
        return header + rest

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


def _recv_exactly(sock, n: int) -> bytes:
    """Read exactly n bytes from sock, returning b'' on clean close."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return b""
        buf += chunk
    return buf
