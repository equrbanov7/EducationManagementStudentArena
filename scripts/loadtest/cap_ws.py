"""Minimal WebSocket (RFC 6455) müştərisi — locust/gevent üçün, əlavə paketsiz.

Locust gevent monkey-patch edir, ona görə stdlib `socket`/`ssl` kooperativdir.
Yalnız mətn (JSON) kadrları; ping-ə pong qaytarılır; fraqmentli mesajlar yığılır.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
from urllib.parse import urlparse


class WSClosed(Exception):
    """Bağlantı bağlandı və ya handshake rədd edildi."""


class WS:
    def __init__(self, url, headers=None, timeout=30, cafile=None):
        parsed = urlparse(url)
        secure = parsed.scheme == "wss"
        port = parsed.port or (443 if secure else 80)
        sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
        if secure:
            ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl._create_unverified_context()
            sock = ctx.wrap_socket(sock, server_hostname=parsed.hostname)
        self.sock = sock
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {parsed.netloc}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ] + [f"{k}: {v}" for k, v in (headers or {}).items()]
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WSClosed("handshake: connection closed")
            head += chunk
        head, _sep, self.buf = head.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status + " ":
            self.sock.close()
            raise WSClosed(f"handshake: {status}")

    def settimeout(self, seconds):
        self.sock.settimeout(seconds)

    def send_json(self, obj):
        self._send(0x1, json.dumps(obj).encode())

    def _send(self, opcode, payload):
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSClosed("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv_json(self):
        """Növbəti JSON mesajı (bloklayır; socket timeout-u `socket.timeout` qaldırır)."""
        message = b""
        while True:
            b1, b2 = self._read(2)
            opcode = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                raise WSClosed(f"closed by server: {code}")
            if opcode == 0x9:
                self._send(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            message += payload
            if b1 & 0x80:
                return json.loads(message.decode())

    def close(self):
        try:
            self._send(0x8, struct.pack("!H", 1000))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
