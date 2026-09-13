"""
İnfrastruktur konfiqurasiya qapıları (Codex audit 2026-09-13: §22, P2-08,
§7, P2-10, P1-07).

Bu testlər DB-siz, yalnız repo fayllarını oxuyur: docker-compose.prod.yml
(PyYAML ilə parse), docker/Dockerfile.prod, requirements/base.txt, setup.cfg,
pyproject.toml. Məqsəd — audit düzəlişlərinin geri sürüşməsinin qarşısını
almaqdır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"

_DEFAULT_RE = re.compile(r"^\$\{[A-Z0-9_]+:-(?P<default>[^}]*)\}$")
_SIZE_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]*)$")
_UNIT_FACTORS = {
    "": 1,
    "b": 1,
    "k": 1000,
    "kb": 1000,
    "m": 1000**2,
    "mb": 1000**2,
    "g": 1000**3,
    "gb": 1000**3,
}


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _interpolation_default(value: str) -> str:
    """`${VAR:-default}` → `default`; interpolyasiyasız dəyər olduğu kimi."""
    match = _DEFAULT_RE.match(value.strip())
    return match.group("default") if match else value.strip()


def _size_to_bytes(text: str) -> int:
    """Redis (`3gb`) və docker (`4096M`) ölçü yazılışlarını baytа çevirir."""
    match = _SIZE_RE.match(text.strip())
    assert match, f"ölçü oxunmadı: {text!r}"
    unit = match.group("unit").lower()
    assert unit in _UNIT_FACTORS, f"naməlum vahid: {text!r}"
    return int(float(match.group("num")) * _UNIT_FACTORS[unit])


def _duration_seconds(text: str) -> float:
    match = re.match(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$", text.strip())
    assert match, f"müddət oxunmadı: {text!r}"
    factor = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[match.group(2)]
    return float(match.group(1)) * factor


# ── §22 — Celery servislərində healthcheck ────────────────────────────────


@pytest.mark.parametrize("service", ["celery_worker", "celery_worker_heavy"])
def test_celery_workers_have_node_scoped_ping_healthcheck(service):
    healthcheck = _compose()["services"][service].get("healthcheck")
    assert healthcheck, f"{service}: healthcheck yoxdur (§22)"

    test = healthcheck["test"]
    assert test[0] == "CMD-SHELL"
    command = test[1]
    assert "celery -A config inspect ping" in command
    # Yalnız BU konteynerin node-una ünvanlanır; `$$` compose-da literal `$`-a
    # çevrilir, shell isə HOSTNAME-i konteyner id-si ilə doldurur.
    assert "-d celery@$$HOSTNAME" in command
    assert "--timeout" in command
    assert _duration_seconds(healthcheck["interval"]) >= 60, "Django yükləyən yoxlama 60s-dən sıx olmamalıdır"
    assert _duration_seconds(healthcheck["timeout"]) >= 20
    assert _duration_seconds(healthcheck["start_period"]) >= 60
    assert int(healthcheck["retries"]) >= 2


def test_celery_beat_has_schedule_freshness_healthcheck():
    service = _compose()["services"]["celery_beat"]
    healthcheck = service.get("healthcheck")
    assert healthcheck, "celery_beat: healthcheck yoxdur (§22)"

    schedule_path = None
    command = service["command"]
    if "--schedule" in command:
        schedule_path = command[command.index("--schedule") + 1]
    assert schedule_path, "beat `--schedule <fayl>` ilə işləməlidir ki, təzəlik yoxlanıla bilsin"

    test = healthcheck["test"]
    assert test[0] == "CMD-SHELL"
    probe = test[1]
    assert "find" in probe and "-mmin" in probe, "beat yoxlaması schedule faylının mtime-ına baxmalıdır"
    assert Path(schedule_path).name in probe
    # Beat worker deyil — `inspect ping` ona cavab vermir; yanlış yoxlama olmasın.
    assert "inspect ping" not in probe
    assert _duration_seconds(healthcheck["interval"]) >= 60
    assert _duration_seconds(healthcheck["start_period"]) >= 60


# ── P2-08 — Redis maxmemory qeydi və limit münasibəti ─────────────────────


def test_redis_maxmemory_default_is_below_container_memory_limit():
    redis = _compose()["services"]["redis"]
    command = redis["command"]
    assert "--maxmemory" in command
    maxmemory = _size_to_bytes(_interpolation_default(command[command.index("--maxmemory") + 1]))
    mem_limit = _size_to_bytes(_interpolation_default(redis["deploy"]["resources"]["limits"]["memory"]))

    assert maxmemory < mem_limit, "REDIS_MAXMEMORY defoltu REDIS_MEM_LIMIT-dən kiçik olmalıdır (OOM-kill riski)"
    # Broker (DB 2) üçün eviction təhlükəlidir — siyasət noeviction qalmalıdır.
    assert command[command.index("--maxmemory-policy") + 1] == "noeviction"


def test_redis_section_comment_no_longer_claims_maxmemory_is_unset():
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    before = text.split("\n  redis:\n", 1)[0]
    closing = before.rfind("  # ─────")
    opening = before.rfind("  # ─────", 0, closing)
    header = before[opening:closing]
    assert "Redis — channel layer" in header
    assert "QƏSDƏN təyin edilməyib" not in header, "P2-08: köhnə, zidd qeyd geri qayıdıb"
    assert "noeviction" in header


# ── P1-07 — build-info image-ə yazılır ─────────────────────────────────────


def test_compose_passes_build_git_sha_to_the_image_build():
    compose = _compose()
    for service in ("app", "celery_worker", "celery_worker_heavy", "celery_beat"):
        args = compose["services"][service]["build"]["args"]
        assert "BUILD_GIT_SHA" in args, f"{service}: BUILD_GIT_SHA build arg-ı yoxdur"
        assert _interpolation_default(args["BUILD_GIT_SHA"]) == "unknown"


def test_dockerfile_writes_build_info_after_project_copy():
    dockerfile = (ROOT / "docker/Dockerfile.prod").read_text(encoding="utf-8")
    assert "ARG BUILD_GIT_SHA=unknown" in dockerfile
    assert "/app/docker/build-info.sh /app/build-info.json" in dockerfile
    # SHA dəyişəndə yalnız kiçik lay yenidən qurulsun: ARG pip layından SONRA.
    assert dockerfile.index("ARG BUILD_GIT_SHA") > dockerfile.index("requirements/production.txt")
    assert dockerfile.index("ARG BUILD_GIT_SHA") > dockerfile.index("COPY --chown=appuser:appgroup . /app/")
    assert (ROOT / "docker/build-info.sh").exists()
    assert "build-info" not in (ROOT / ".dockerignore").read_text(encoding="utf-8")


# ── P2-10 — setuptools ─────────────────────────────────────────────────────


def test_image_upgrades_pip_setuptools_wheel_and_requirements_pin_setuptools_floor():
    dockerfile = (ROOT / "docker/Dockerfile.prod").read_text(encoding="utf-8")
    assert "pip install --no-cache-dir --upgrade pip setuptools wheel" in dockerfile

    base = (ROOT / "requirements/base.txt").read_text(encoding="utf-8")
    match = re.search(r"^setuptools>=(\d+)\.(\d+)\.(\d+)\s*$", base, flags=re.MULTILINE)
    assert match, "requirements/base.txt: setuptools>=… floor yoxdur (P2-10)"
    assert tuple(int(part) for part in match.groups()) >= (78, 1, 1)


# ── §7 — pytest konfiqinin tək mənbəyi ─────────────────────────────────────


def test_pytest_config_lives_only_in_pyproject():
    setup_cfg = (ROOT / "setup.cfg").read_text(encoding="utf-8")
    assert not re.search(
        r"^\[tool:pytest\]", setup_cfg, flags=re.MULTILINE
    ), "§7: setup.cfg-də dublikat pytest bölməsi (pytest xəbərdarlıq verir)"

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.pytest.ini_options]" in pyproject
    ini = pyproject.split("[tool.pytest.ini_options]", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^\s*"timeout\(', ini, flags=re.MULTILINE), "§7: `timeout` markeri qeydə alınmayıb"
    assert re.search(r'^\s*"postgres:', ini, flags=re.MULTILINE)


def test_ci_unit_tests_install_pytest_timeout_plugin():
    workflow = (ROOT / ".github/workflows/_unit-tests.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements/test.txt").read_text(encoding="utf-8")
    assert "pip install -r requirements/test.txt" in workflow
    assert re.search(r"^pytest-timeout==", requirements, flags=re.MULTILINE)
