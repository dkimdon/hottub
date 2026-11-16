"""Shared test helpers."""

import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bwa.server import Server


class ServerThread:
    """Context manager that runs a simulated spa on a free local port."""

    def __init__(self, status_interval: float = 0.05) -> None:
        self.server = Server(port=0, status_interval=status_interval)
        self.port = self.server.port
        self.status = self.server.status
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "ServerThread":
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self.server.stop()
        self._thread.join(timeout=2)
