"""EMSArena ARP agenti — host neighbor cədvəlindən IP→MAC axtarış xidməti.

İmtahan zalı kompüterləri serverlə eyni L2 seqmentdə olduğu üçün onların real
MAC ünvanları host-un ARP cədvəlində (``/proc/net/arp``) görünür. Bu agent
``network_mode: host`` ilə işləyir və app konteynerinə kiçik JSON endpoint
verir: ``GET /mac?ip=<ipv4>`` → ``{"ip": ..., "mac": "AA:BB:..." | null}``.

Təhlükəsizlik: yalnız docker bridge gateway ünvanına bind olur
(``ARP_AGENT_BIND``, default 172.18.0.1) — LAN müştəriləri bu ünvana çata
bilmir; MAC siyahısı kənara sızmır. İstehlakçı:
``apps/exams/services/exam_center_gate.py`` (``resolve_client_mac``).

Yalnız stdlib istifadə olunur — ``python:3.12-alpine`` image-i build-siz,
bind-mount ilə işlədir (bax docker-compose.prod.yml ``arp-agent`` servisi).
"""

import ipaddress
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BIND = os.getenv("ARP_AGENT_BIND", "172.18.0.1")
PORT = int(os.getenv("ARP_AGENT_PORT", "8953"))

# /proc/net/arp bayraqları: 0x2 = ATF_COM (tam/həll olunmuş qeyd).
ATF_COM = 0x2
EMPTY_MAC = "00:00:00:00:00:00"


def mac_for_ip(ip: str) -> str | None:
    """Host ARP cədvəlində IP üçün tam (complete) MAC qeydini qaytarır."""
    with open("/proc/net/arp") as fh:
        next(fh)  # başlıq sətri
        for line in fh:
            parts = line.split()
            # Sütunlar: IP, HW type, Flags, HW address, Mask, Device
            if len(parts) >= 4 and parts[0] == ip:
                try:
                    flags = int(parts[2], 16)
                except ValueError:
                    continue
                mac = parts[3].upper()
                if flags & ATF_COM and mac != EMPTY_MAC:
                    return mac
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler API adı
        url = urlparse(self.path)
        if url.path != "/mac":
            self.send_error(404)
            return
        ip = (parse_qs(url.query).get("ip") or [""])[0]
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            self.send_error(400)
            return
        body = json.dumps({"ip": ip, "mac": mac_for_ip(ip)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # sorğu başına stdout səs-küyünü söndür
        pass


if __name__ == "__main__":
    print(f"arp-agent: {BIND}:{PORT} ünvanında dinləyir", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
