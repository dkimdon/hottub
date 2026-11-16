"""Protocol proxy — sits between a real spa and a client, logging all messages.

Useful for debugging and protocol inspection.

Usage::

    proxy = Proxy("192.168.1.50")
    proxy.run()   # blocks; Ctrl-C to stop
"""

import socket
import threading

from .message import Message, InvalidMessage, split_frames


class Proxy:
    """TCP proxy that logs all BWA messages in both directions."""

    def __init__(self, host: str, port: int = 4257, listen_port: int = 4257) -> None:
        self.host = host
        self.port = port
        self.listen_port = listen_port

    def run(self) -> None:
        """Accept one client connection, proxy it, then exit."""
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind(("", self.listen_port))
        listen_sock.listen(1)
        print(f"[Proxy] Listening on port {self.listen_port}, forwarding to {self.host}:{self.port}")

        client_sock, addr = listen_sock.accept()
        print(f"[Proxy] Client connected from {addr}")
        server_sock = socket.create_connection((self.host, self.port), timeout=10)
        server_sock.settimeout(None)

        threads = [
            threading.Thread(
                target=self._shuffle, args=(client_sock, server_sock, "Client→Spa"), daemon=True
            ),
            threading.Thread(
                target=self._shuffle, args=(server_sock, client_sock, "Spa→Client"), daemon=True
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        client_sock.close()
        server_sock.close()
        listen_sock.close()

    def _shuffle(self, src: socket.socket, dst: socket.socket, tag: str) -> None:
        buf = b""
        try:
            while True:
                chunk = src.recv(256)
                if not chunk:
                    dst.close()
                    break
                dst.sendall(chunk)
                frames, buf = split_frames(buf + chunk)
                for frame in frames:
                    try:
                        print(f"[Proxy] {tag}: {Message.parse(frame)!r}")
                    except InvalidMessage as e:
                        print(f"[Proxy] {tag}: invalid message: {e} ({frame.hex(' ')})")
        except OSError:
            pass
