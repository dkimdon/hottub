"""CRC-8 implementation matching the Balboa Worldwide App protocol.

Uses polynomial 0x07, initial value 0x02, and final XOR 0x02.
Matches the Ruby digest-crc CRC8 with INIT_CRC=0x02, XOR_MASK=0x02.
"""

_POLY = 0x07

def _build_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ _POLY
            else:
                crc = crc << 1
            crc &= 0xFF
        table.append(crc)
    return table

_TABLE = _build_table()


def checksum(data: bytes) -> int:
    """Compute the BWA CRC-8 checksum over data, returning a single byte integer."""
    crc = 0x02  # INIT_CRC
    for byte in data:
        crc = _TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0x02  # XOR_MASK
