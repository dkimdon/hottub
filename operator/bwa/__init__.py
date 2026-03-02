"""bwa — Python library for Balboa Worldwide App spa/hot tub protocol.

Quick start::

    from bwa.client import Client
    from bwa.discovery import find_spa

    ip = find_spa()
    with Client(ip) as spa:
        status = spa.poll_until_status()
        print(status)
        spa.set_temperature(104)
"""

from .client import Client
from .discovery import discover, find_spa
from . import messages

__all__ = ["Client", "discover", "find_spa", "messages"]
