"""
Opt-in ASGI server açarı (ASGI_SERVER=daphne|uvicorn, ASGI_WORKERS=N).

DB-siz qapılar: defolt prod davranışı (Daphne, 1 proses) dəyişmir; uvicorn
budağı Daphne ilə eyni müştəri İP-si / WS limitləri / shutdown büdcəsini
saxlayır. Bax docker/prod-entrypoint.sh və docs/operations/ASGI_SERVER.md.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker/prod-entrypoint.sh"
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"


def _app_env() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))["services"]["app"]["environment"]


def _uvicorn_block() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    start = text.index("exec uvicorn")
    return text[start : text.index("config.asgi:application", start)]


def test_compose_defaults_keep_daphne_single_process():
    env = _app_env()
    assert env["ASGI_SERVER"] == "${ASGI_SERVER:-daphne}"
    assert env["ASGI_WORKERS"] == "${ASGI_WORKERS:-1}"


@pytest.mark.parametrize(
    "flag",
    [
        "--lifespan off",
        "--proxy-headers",
        '--forwarded-allow-ips "${ASGI_FORWARDED_ALLOW_IPS:-*}"',
        '--workers "$ASGI_WORKERS"',
        "--ws websockets-sansio",
        # Daphne defoltları: --websocket-max-message-size 1 MiB, ping 20/30 s, deflate yox.
        "--ws-max-size 1048576",
        "--ws-ping-interval 20",
        "--ws-ping-timeout 30",
        "--ws-per-message-deflate false",
        # compose stop_grace_period invariantı DAPHNE_APPLICATION_CLOSE_TIMEOUT-a bağlıdır.
        '--timeout-graceful-shutdown "${DAPHNE_APPLICATION_CLOSE_TIMEOUT:-120}"',
        "--timeout-worker-healthcheck",
    ],
)
def test_uvicorn_flags_mirror_daphne(flag):
    assert flag in _uvicorn_block()


def _write_stub(directory: Path, name: str) -> None:
    stub = directory / name
    stub.write_text(f'#!/bin/sh\necho "{name} $*"\n', encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_entrypoint(tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    sh = shutil.which("sh")
    if not sh:  # pragma: no cover
        pytest.skip("sh yoxdur")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("daphne", "uvicorn"):
        _write_stub(bin_dir, name)
    run_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "RUN_RELEASE_ON_START": "false",
        **env,
    }
    return subprocess.run([sh, str(ENTRYPOINT)], env=run_env, capture_output=True, text=True, timeout=30)


def test_entrypoint_defaults_to_daphne(tmp_path):
    result = _run_entrypoint(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "daphne -b 0.0.0.0 -p 8000 --proxy-headers" in result.stdout
    assert "uvicorn " not in result.stdout


def test_entrypoint_runs_uvicorn_with_workers(tmp_path):
    result = _run_entrypoint(tmp_path, ASGI_SERVER="uvicorn", ASGI_WORKERS="3")
    assert result.returncode == 0, result.stderr
    line = next(row for row in result.stdout.splitlines() if row.startswith("uvicorn "))
    assert "--workers 3 " in line
    assert "--forwarded-allow-ips * " in line
    assert "--timeout-graceful-shutdown 120 " in line
    assert line.rstrip().endswith("--access-log config.asgi:application")


@pytest.mark.parametrize(
    "env",
    [
        {"ASGI_SERVER": "gunicorn"},
        {"ASGI_SERVER": "uvicorn", "ASGI_WORKERS": "0"},
        {"ASGI_SERVER": "uvicorn", "ASGI_WORKERS": "two"},
        {"ASGI_SERVER": "daphne", "ASGI_WORKERS": "2"},
    ],
)
def test_entrypoint_rejects_invalid_switch(tmp_path, env):
    result = _run_entrypoint(tmp_path, **env)
    assert result.returncode == 64
    assert "daphne " not in result.stdout and "uvicorn " not in result.stdout


@pytest.mark.parametrize(
    "xff",
    ["203.0.113.7", "203.0.113.7, 10.0.0.1", "2001:db8::1"],
)
def test_uvicorn_proxy_headers_give_same_client_as_daphne(xff):
    """Django-nun REMOTE_ADDR-i və WS scope["client"] hər iki serverdə eynidir."""
    pytest.importorskip("uvicorn")
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from daphne.utils import parse_x_forwarded_for

    daphne_addr, _ = parse_x_forwarded_for(
        {b"x-forwarded-for": [xff.encode()]}, original_addr=["172.18.0.5", 50000], original_scheme="http"
    )
    seen = {}

    async def app(scope, receive, send):
        seen.update(client=scope["client"], scheme=scope["scheme"])

    middleware = ProxyHeadersMiddleware(app, trusted_hosts="*")
    scope = {
        "type": "http",
        "scheme": "http",
        "client": ("172.18.0.5", 50000),
        "headers": [(b"x-forwarded-for", xff.encode()), (b"x-forwarded-proto", b"https")],
    }
    asyncio.run(middleware(scope, None, None))
    assert list(seen["client"]) == list(daphne_addr)
    assert seen["scheme"] == "https"


def test_asgi_threads_sizes_uvicorn_default_executor(monkeypatch):
    from config.asgi import _apply_asgi_threads_under_uvicorn

    async def probe():
        _apply_asgi_threads_under_uvicorn()
        return asyncio.get_running_loop()._default_executor

    monkeypatch.setenv("ASGI_THREADS", "7")
    monkeypatch.delenv("ASGI_SERVER", raising=False)
    assert asyncio.run(probe()) is None  # Daphne/test: toxunulmur

    monkeypatch.setenv("ASGI_SERVER", "uvicorn")
    executor = asyncio.run(probe())
    assert executor is not None and executor._max_workers == 7


def test_uvicorn_stack_is_pinned_in_locks():
    for lock in ("production.lock", "test.lock"):
        text = (ROOT / "requirements" / lock).read_text(encoding="utf-8")
        for package in ("uvicorn==", "httptools==", "websockets==", "uvloop==", "h11=="):
            assert f"\n{package}" in text, f"{lock}: {package} pin yoxdur"
