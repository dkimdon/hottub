"""UDP spa discovery.

Sends a broadcast to port 30303 and collects responses from Balboa devices
(identified by their MAC prefix 00-15-27).
"""

import socket
from typing import Optional

DISCOVERY_PORT = 30303
DISCOVERY_MESSAGE = b"Discovery: Who is out there?"
BALBOA_MAC_PREFIX = "00-15-27-"


def discover(timeout: float = 5.0, exhaustive: bool = False) -> dict[str, str]:
    """Broadcast a discovery request and return a dict of {ip: name}.

    Args:
        timeout:    Seconds to wait for responses after the last one received.
        exhaustive: If True, keep waiting for more devices after finding one.

    Returns:
        Dict mapping spa IP address strings to spa name strings (e.g. "BWGSPA").
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(("", 0))

    sock.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))

    spas: dict[str, str] = {}
    try:
        while True:
            data, (ip, _) = sock.recvfrom(64)
            text = data.decode("ascii", errors="replace")
            lines = text.split("\r\n")
            if len(lines) < 2:
                continue
            name = lines[0].strip()
            mac = lines[1].strip()
            if mac.startswith(BALBOA_MAC_PREFIX):
                spas[ip] = name
                if not exhaustive:
                    break
    except socket.timeout:
        pass
    finally:
        sock.close()

    return spas


def find_spa(timeout: float = 5.0) -> Optional[str]:
    """Return the IP address of the first spa found, or None."""
    found = discover(timeout=timeout)
    if found:
        return next(iter(found))
    return None
