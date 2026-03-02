"""Protocol proxy — sits between a real spa and a client, logging all messages.

Useful for debugging and protocol inspection.

Usage::

    proxy = Proxy("192.168.1.50")
    proxy.run()   # blocks; Ctrl-C to stop
"""

import select
import socket
import threading

from .message import Message, InvalidMessage

FRAME_START = 0x7E


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
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((self.host, self.port))

        t1 = threading.Thread(
            target=self._shuffle, args=(client_sock, server_sock, "Client→Spa"), daemon=True
        )
        t2 = threading.Thread(
            target=self._shuffle, args=(server_sock, client_sock, "Spa→Client"), daemon=True
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

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
                buf += chunk
                buf, _ = self._drain_frames(buf, tag)
                dst.sendall(chunk)
        except OSError:
            pass

    def _drain_frames(self, buf: bytes, tag: str) -> tuple[bytes, list]:
        msgs = []
        while len(buf) >= 2:
            if buf[0] != FRAME_START:
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
                print(f"[Proxy] {tag}: {msg!r}")
                msgs.append(msg)
            except InvalidMessage as e:
                print(f"[Proxy] {tag}: invalid message: {e}")
        return buf, msgs
