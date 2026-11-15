"""ConfigurationRequest message (0x0a 0xbf 0x04).

Sent by the client to request hardware configuration from the spa.
No payload.
"""

from ..message import Message


class ConfigurationRequest(Message):
    MESSAGE_TYPE = bytes([0x0A, 0xBF, 0x04])
    MESSAGE_LENGTH = 0

    def __repr__(self) -> str:
        return "<ConfigurationRequest>"
