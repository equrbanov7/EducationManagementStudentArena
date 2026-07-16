from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_production_nginx_is_a_direct_edge_and_does_not_trust_inbound_proxy_headers():
    config = (ROOT / "docker/nginx/nginx.conf").read_text(encoding="utf-8")

    assert "cloudflare" not in config.lower()
    assert "CF-Connecting-IP" not in config
    assert "set_real_ip_from" not in config
    assert "real_ip_header" not in config
    assert "limit_req_zone  $binary_remote_addr" in config
    assert "limit_conn_zone $binary_remote_addr" in config
    assert config.count("proxy_set_header X-Forwarded-For   $remote_addr;") >= 2
    assert config.count("proxy_set_header X-Forwarded-Proto $scheme;") >= 2
    assert "$proxy_add_x_forwarded_for" not in config


def test_direct_deploy_is_fail_closed_and_removes_legacy_cloudflare_firewall_rules():
    script = (ROOT / "scripts/deploy/remote_deploy.sh").read_text(encoding="utf-8")

    assert 'EDGE_PROXY_MODE="${EDGE_PROXY_MODE:-direct}"' in script
    assert 'EDGE_PROXY_MODE" != "direct"' in script
    assert "sync_cloudflare_networks.py" not in script
    assert "configure_cloudflare_firewall_family" not in script
    assert "remove_edge_firewall_family iptables EMSARENA-CF-WEB" in script
    assert "remove_edge_firewall_family ip6tables EMSARENA-CF-WEB6" in script
    assert "X-Forwarded-Proto: https" not in script
    assert "validate_direct_tls.sh" in script
    assert "openssl req -x509" not in script


def test_direct_deploy_requires_dns_to_resolve_only_to_declared_origin_addresses():
    script = (ROOT / "scripts/deploy/remote_deploy.sh").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "DIRECT_ORIGIN_IPS" in script
    assert "preflight_direct_dns" in script
    assert "DIRECT_ORIGIN_IPS" in env_example
    assert "EDGE_PROXY_MODE=direct" in env_example
    assert "EDGE_PROXY_MODE=cloudflare" not in env_example


def test_deploy_recreates_nginx_when_single_file_bind_mount_is_stale():
    script = (ROOT / "scripts/deploy/remote_deploy.sh").read_text(encoding="utf-8")
    refresh = script.split("refresh_nginx_upstream() {", 1)[1].split("\n}", 1)[0]

    assert 'sha256sum "$NGINX_CONFIG_FILE"' in refresh
    assert "sha256sum /etc/nginx/conf.d/default.conf" in refresh
    assert '"$host_config_hash" != "$container_config_hash"' in refresh
    assert "run --rm --no-deps nginx nginx -t" in refresh
    assert "up -d --no-deps --force-recreate nginx" in refresh


def test_obsolete_cloudflare_runtime_assets_are_absent():
    assert not (ROOT / "docker/nginx/cloudflare-realip.conf").exists()
    assert not (ROOT / "scripts/deploy/sync_cloudflare_networks.py").exists()


def _openssl(*args, cwd=None):
    subprocess.run(
        ["openssl", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is required")
def test_tls_validator_accepts_matching_leaf_and_intermediate_fullchain(tmp_path):
    root_key = tmp_path / "root.key"
    root_cert = tmp_path / "root.crt"
    int_key = tmp_path / "intermediate.key"
    int_csr = tmp_path / "intermediate.csr"
    int_cert = tmp_path / "intermediate.crt"
    leaf_key = tmp_path / "leaf.key"
    leaf_csr = tmp_path / "leaf.csr"
    leaf_cert = tmp_path / "leaf.crt"
    fullchain = tmp_path / "fullchain.crt"

    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=EMSArena Test Root",
        "-keyout",
        str(root_key),
        "-out",
        str(root_cert),
        "-days",
        "30",
    )
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=EMSArena Test Intermediate",
        "-keyout",
        str(int_key),
        "-out",
        str(int_csr),
    )
    int_ext = tmp_path / "intermediate.ext"
    int_ext.write_text(
        "basicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\n",
        encoding="utf-8",
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        str(int_csr),
        "-CA",
        str(root_cert),
        "-CAkey",
        str(root_key),
        "-CAcreateserial",
        "-out",
        str(int_cert),
        "-days",
        "20",
        "-extfile",
        str(int_ext),
    )
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=emsarena.test",
        "-keyout",
        str(leaf_key),
        "-out",
        str(leaf_csr),
    )
    leaf_ext = tmp_path / "leaf.ext"
    leaf_ext.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "subjectAltName=DNS:emsarena.test\n"
        "extendedKeyUsage=serverAuth\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n",
        encoding="utf-8",
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        str(leaf_csr),
        "-CA",
        str(int_cert),
        "-CAkey",
        str(int_key),
        "-CAcreateserial",
        "-out",
        str(leaf_cert),
        "-days",
        "10",
        "-extfile",
        str(leaf_ext),
    )
    fullchain.write_bytes(leaf_cert.read_bytes() + b"\n" + int_cert.read_bytes())

    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/deploy/validate_direct_tls.sh"),
            str(fullchain),
            str(leaf_key),
            "emsarena.test",
            "3600",
            "false",
            str(root_cert),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "validated" in result.stdout


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is required")
def test_tls_validator_rejects_self_signed_production_certificate(tmp_path):
    key = tmp_path / "self.key"
    cert = tmp_path / "self.crt"
    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=localhost",
        "-addext",
        "subjectAltName=DNS:localhost",
        "-keyout",
        str(key),
        "-out",
        str(cert),
        "-days",
        "10",
    )

    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/deploy/validate_direct_tls.sh"),
            str(cert),
            str(key),
            "localhost",
            "3600",
            "false",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Self-signed" in result.stderr
