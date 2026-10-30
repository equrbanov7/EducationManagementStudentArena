"""Keep the narrow Twisted HTTP/2 advisory exception behind its real boundary."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_twisted_has_no_public_listener_or_host_network():
    services = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())["services"]
    app = services["app"]
    assert not app.get("ports"), "Public app ports invalidate GHSA-vpp8-g58w-m8mp exception"
    assert not app.get("network_mode"), "App must remain behind the nginx bridge"
    assert app["networks"] == ["emsarena-network"]


def test_every_nginx_app_proxy_speaks_http11():
    text = (ROOT / "docker/nginx/nginx.conf").read_text()
    lines = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    proxies = [index for index, line in enumerate(lines) if line.startswith("proxy_pass ")]
    assert proxies, "Expected nginx reverse proxy boundary"
    for index in proxies:
        end = next(position for position in range(index + 1, len(lines)) if lines[position] == "}")
        assert "proxy_http_version 1.1;" in lines[index + 1 : end]
    assert not any(re.search(r"(?:grpc_pass|proxy_http_version\s+2|h2c)", line) for line in lines)


def test_daphne_starts_without_a_direct_tls_http2_endpoint():
    text = (ROOT / "docker/prod-entrypoint.sh").read_text()
    command = text.split("exec daphne", 1)[1]
    assert "-p 8000" in command
    assert not re.search(r"(?:^|\s)(?:-e|--endpoint|--ssl)(?:\s|=)", command)
