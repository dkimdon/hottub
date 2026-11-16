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
MIN_LENGTH = 5  # L for a message with an empty payload


class InvalidMessage(Exception):
    def __init__(self, reason: str, raw: bytes):
        super().__init__(reason)
        self.raw = raw


def build_frame(message_type: bytes, payload: bytes = b"") -> bytes:
    """Wrap a 3-byte message type and payload in length, CRC and delimiters."""
    inner = bytes([len(payload) + MIN_LENGTH]) + message_type + payload
    return bytes([FRAME_START]) + inner + bytes([_crc.checksum(inner), FRAME_END])


def split_frames(buf: bytes) -> tuple[list[bytes], bytes]:
    """Split a receive buffer into complete frames plus the unconsumed tail.

    Bytes that cannot be the start of a frame are skipped, so a reader that
    has lost alignment (for example after a corrupt frame) finds the next
    frame start instead of treating an end delimiter as a start.
    """
    frames = []
    while len(buf) >= 2:
        # A length byte of 0x7e means we are looking at the previous frame's
        # end delimiter followed by the next frame's start.
        if buf[0] != FRAME_START or buf[1] < MIN_LENGTH or buf[1] == FRAME_START:
            buf = buf[1:]
            continue
        total = buf[1] + 2
        if len(buf) < total:
            break
        frames.append(buf[:total])
        buf = buf[total:]
    return frames, buf


class Message:
    """Base class for all BWA messages."""

    MESSAGE_TYPE: ClassVar[bytes]   # 3-byte type identifier
    MESSAGE_LENGTH: ClassVar[int]   # expected payload byte count

    # Registry populated by __init_subclass__
    _registry: ClassVar[dict[bytes, type[Message]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "MESSAGE_TYPE" in cls.__dict__:
            Message._registry[cls.MESSAGE_TYPE] = cls

    @classmethod
    def parse(cls, frame: bytes) -> "Message":
        """Parse a complete wire frame and return the appropriate Message subclass."""
        if len(frame) < MIN_LENGTH + 2:
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
            raise InvalidMessage(f"Unknown message type {msg_type.hex()}", frame)

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

    def _serialize_payload(self) -> bytes:
        """Subclasses override to encode to payload bytes."""
        return b""

    def to_bytes(self) -> bytes:
        """Encode this message to a complete wire frame."""
        return build_frame(self.MESSAGE_TYPE, self._serialize_payload())

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
