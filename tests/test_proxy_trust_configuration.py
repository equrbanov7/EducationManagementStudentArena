from __future__ import annotations

from pathlib import Path

import pytest

from scripts.deploy.sync_cloudflare_networks import _parse_networks, render_nginx

ROOT = Path(__file__).resolve().parents[1]


def test_cloudflare_network_parser_rejects_wrong_address_family():
    with pytest.raises(ValueError, match="expected IPv4"):
        _parse_networks("173.245.48.0/20 2606:4700::/32", version=4)


def test_rendered_realip_config_has_strict_header_and_all_networks():
    ipv4 = _parse_networks(
        " ".join(
            [
                "173.245.48.0/20",
                "103.21.244.0/22",
                "103.22.200.0/22",
                "103.31.4.0/22",
                "141.101.64.0/18",
                "108.162.192.0/18",
                "190.93.240.0/20",
                "188.114.96.0/20",
                "197.234.240.0/22",
                "198.41.128.0/17",
            ]
        ),
        version=4,
    )
    ipv6 = _parse_networks(
        "2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32 2a06:98c0::/29",
        version=6,
    )

    rendered = render_nginx([*ipv4, *ipv6])

    assert "set_real_ip_from 173.245.48.0/20;" in rendered
    assert "set_real_ip_from 2606:4700::/32;" in rendered
    assert rendered.count("real_ip_header CF-Connecting-IP;") == 1
    assert "real_ip_recursive on;" in rendered


def test_production_nginx_uses_validated_remote_addr_for_forwarding_and_limits():
    config = (ROOT / "docker/nginx/nginx.conf").read_text(encoding="utf-8")

    assert "include /etc/nginx/trusted_proxies/cloudflare-realip.conf;" in config
    assert "limit_req_zone  $binary_remote_addr" in config
    assert "limit_conn_zone $binary_remote_addr" in config
    assert config.count("proxy_set_header X-Forwarded-For   $remote_addr;") >= 2
    assert "$proxy_add_x_forwarded_for" not in config
    assert "$http_cf_connecting_ip" not in config


def test_deploy_requires_explicit_supported_edge_mode_and_no_spoofed_scheme_header():
    script = (ROOT / "scripts/deploy/remote_deploy.sh").read_text(encoding="utf-8")

    assert 'EDGE_PROXY_MODE="${EDGE_PROXY_MODE:-cloudflare}"' in script
    assert 'EDGE_PROXY_MODE" != "cloudflare"' in script
    assert 'EDGE_PROXY_MODE" != "direct"' in script
    assert "X-Forwarded-Proto: https" not in script
    assert "sync_cloudflare_networks.py" in script
