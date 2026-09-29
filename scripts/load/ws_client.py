"""Minimal asyncio WebSocket client (RFC 6455) — yalnız stdlib.

Yük testi üçün (``live_exam_load.py``): venv-də ``websockets`` / ``aiohttp`` yoxdur, yeni
asılılıq əlavə etməmək üçün mətn kadrları, fraqmentasiya, ping/pong və close dəstəklənir.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
from urllib.parse import urlsplit

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WSHandshakeError(Exception):
    """Server handshake-i rədd etdi (məs. 403 — auth/limit)."""

    @property
    def status(self) -> int:
        return int(self.args[0]) if self.args else 0


class WSClosed(Exception):
    """Socket bağlandı; ``code`` — close kodu (None → TCP qopdu)."""

    @property
    def code(self) -> int | None:
        return self.args[0] if self.args else None


def _mask(payload: bytes, key: bytes) -> bytes:
    return bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))


def _frame(opcode: int, payload: bytes) -> bytes:
    header = bytearray([0x80 | opcode])
    size = len(payload)
    if size < 126:
        header.append(0x80 | size)
    elif size < 65536:
        header.append(0x80 | 126)
        header += struct.pack("!H", size)
    else:
        header.append(0x80 | 127)
        header += struct.pack("!Q", size)
    key = os.urandom(4)
    return bytes(header) + key + _mask(payload, key)


class WSClient:
    def __init__(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 15.0):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.closed = False
        self.close_code: int | None = None

    async def connect(self) -> None:
        parts = urlsplit(self.url)
        host, port = parts.hostname, parts.port or (443 if parts.scheme == "wss" else 80)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(host, port), self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            *[f"{name}: {value}" for name, value in self.headers.items()],
        ]
        self.writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        await self.writer.drain()
        status_line = (await asyncio.wait_for(self.reader.readline(), self.timeout)).decode("latin-1")
        while True:  # başlıqları at
            header = await asyncio.wait_for(self.reader.readline(), self.timeout)
            if header in (b"\r\n", b"\n", b""):
                break
        parts_line = status_line.split()
        status = int(parts_line[1]) if len(parts_line) > 1 and parts_line[1].isdigit() else 0
        if status != 101:
            self.writer.close()
            raise WSHandshakeError(status, status_line.strip())

    async def send_json(self, data) -> None:
        await self.send_text(json.dumps(data))

    async def send_text(self, text: str) -> None:
        if self.closed or self.writer is None:
            raise WSClosed(self.close_code)
        self.writer.write(_frame(OP_TEXT, text.encode("utf-8")))
        await self.writer.drain()

    async def _read_frame(self):
        head = await self.reader.readexactly(2)
        fin, opcode = head[0] & 0x80, head[0] & 0x0F
        masked, size = head[1] & 0x80, head[1] & 0x7F
        if size == 126:
            size = struct.unpack("!H", await self.reader.readexactly(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", await self.reader.readexactly(8))[0]
        key = await self.reader.readexactly(4) if masked else None
        payload = await self.reader.readexactly(size)
        return bool(fin), opcode, _mask(payload, key) if key else payload

    async def recv_text(self) -> str:
        """Növbəti mətn mesajı; bağlananda ``WSClosed``."""
        buffer = b""
        while True:
            try:
                fin, opcode, payload = await self._read_frame()
            except (asyncio.IncompleteReadError, ConnectionError) as exc:
                self.closed = True
                raise WSClosed(self.close_code) from exc
            if opcode == OP_PING:
                self.writer.write(_frame(OP_PONG, payload))
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                self.close_code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                self.closed = True
                try:
                    self.writer.write(_frame(OP_CLOSE, payload[:2]))
                    self.writer.close()
                except Exception:
                    pass
                raise WSClosed(self.close_code)
            buffer += payload
            if fin:
                return buffer.decode("utf-8")

    async def recv_json(self):
        return json.loads(await self.recv_text())

    async def close(self, code: int = 1000) -> None:
        if self.closed or self.writer is None:
            return
        self.closed = True
        try:
            self.writer.write(_frame(OP_CLOSE, struct.pack("!H", code)))
            await self.writer.drain()
            self.writer.close()
        except Exception:
            pass

    def abort(self) -> None:
        """Wi-Fi qopması kimi — close kadrı göndərmədən TCP-ni kəsir."""
        self.closed = True
        if self.writer is not None:
            self.writer.transport.abort()
