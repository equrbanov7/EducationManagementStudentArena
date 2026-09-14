"""
İnfrastruktur konfiqurasiya qapıları (Codex audit 2026-09-13: §22, P2-08,
§7, P2-10, P1-07).

Bu testlər DB-siz, yalnız repo fayllarını oxuyur: docker-compose.prod.yml
(PyYAML ilə parse), docker/Dockerfile.prod, requirements/base.txt, setup.cfg,
pyproject.toml. Məqsəd — audit düzəlişlərinin geri sürüşməsinin qarşısını
almaqdır.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
REDIS_TEMPLATE_PATH = ROOT / "docker/redis/redis.conf.tmpl"
REDIS_ENTRYPOINT_PATH = ROOT / "docker/redis/entrypoint.sh"
RENDER_TEMPLATE_PATH = ROOT / "docker/render-template.sh"

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
    # 2026-09-14 infra auditi P3-3: seçimlər argv-dən docker/redis/redis.conf.tmpl
    # şablonuna keçdi; maxmemory dəyəri compose env REDIS_MAXMEMORY-dən gəlir.
    redis = _compose()["services"]["redis"]
    template = REDIS_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert re.search(r"^maxmemory __REDIS_MAXMEMORY__$", template, flags=re.MULTILINE)
    maxmemory = _size_to_bytes(_interpolation_default(redis["environment"]["REDIS_MAXMEMORY"]))
    mem_limit = _size_to_bytes(_interpolation_default(redis["deploy"]["resources"]["limits"]["memory"]))

    assert maxmemory < mem_limit, "REDIS_MAXMEMORY defoltu REDIS_MEM_LIMIT-dən kiçik olmalıdır (OOM-kill riski)"
    # Broker (DB 2) üçün eviction təhlükəlidir — siyasət noeviction qalmalıdır.
    assert re.search(r"^maxmemory-policy noeviction$", template, flags=re.MULTILINE)
    assert re.search(r"^appendonly yes$", template, flags=re.MULTILINE)


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


# ── 2026-09-13 infra auditi — P2-3 stop_grace_period ──────────────────────
# Docker defoltu SIGTERM-dən 10 s sonra SIGKILL-dir; Daphne close-timeout
# (120 s), Celery warm shutdown (task time_limit 300/900 s) və Postgres
# shutdown-u bundan uzundur — deploy zamanı davam edən imtahan təqdimi/OCR
# kəsilir, Postgres «crash» kimi qalxırdı.


def _env_default(mapping: dict, key: str) -> str:
    return _interpolation_default(str(mapping[key]))


def test_app_stop_grace_period_covers_daphne_application_close_timeout():
    app = _compose()["services"]["app"]
    close_timeout = float(_env_default(app["environment"], "DAPHNE_APPLICATION_CLOSE_TIMEOUT"))
    grace = _duration_seconds(_interpolation_default(app["stop_grace_period"]))
    assert (
        grace >= close_timeout + 10
    ), "P2-3: app.stop_grace_period ≥ DAPHNE_APPLICATION_CLOSE_TIMEOUT + 10 s olmalıdır"


@pytest.mark.parametrize(
    ("service", "minimum_seconds", "reason"),
    [
        ("celery_worker", 300, "CELERY_TASK_TIME_LIMIT (celery_cache.py) — warm shutdown icradakı task-ı bitirir"),
        ("celery_worker_heavy", 900, "heavy task time_limit (apps/exams/tasks.py: OCR/AI/export 900 s)"),
        ("postgres", 60, "smart/fast shutdown checkpoint-i bitirsin — 10 s SIGKILL = WAL bərpası"),
    ],
)
def test_long_running_services_have_stop_grace_period(service, minimum_seconds, reason):
    definition = _compose()["services"][service]
    assert "stop_grace_period" in definition, f"P2-3: {service}.stop_grace_period yoxdur ({reason})"
    assert _duration_seconds(_interpolation_default(definition["stop_grace_period"])) >= minimum_seconds, reason


def test_heavy_worker_grace_matches_task_hard_time_limit_in_source():
    """Heavy task-ların `time_limit` dəyəri dəyişsə compose də dəyişməlidir."""
    tasks_source = (ROOT / "apps/exams/tasks.py").read_text(encoding="utf-8")
    limits = [int(value) for value in re.findall(r"time_limit=(\d+)", tasks_source)]
    assert limits, "apps/exams/tasks.py-də heavy time_limit tapılmadı"
    grace = _duration_seconds(
        _interpolation_default(_compose()["services"]["celery_worker_heavy"]["stop_grace_period"])
    )
    assert grace >= max(limits)


# ── P2-4 — arp-agent gateway ünvanı üçün IPAM pin + sidecar hijyeni ────────


def test_network_ipam_is_pinned_to_the_arp_agent_gateway():
    compose = _compose()
    ipam = compose["networks"]["emsarena-network"].get("ipam", {}).get("config")
    assert ipam, "P2-4: emsarena-network IPAM subnet/gateway pin-lənməyib (arp-agent bind ünvanı sabitdir)"
    gateway = _interpolation_default(ipam[0]["gateway"])
    subnet = _interpolation_default(ipam[0]["subnet"])

    arp_bind = _env_default(compose["services"]["arp-agent"]["environment"], "ARP_AGENT_BIND")
    arp_port = _env_default(compose["services"]["arp-agent"]["environment"], "ARP_AGENT_PORT")
    agent_url = _env_default(compose["services"]["app"]["environment"], "EXAM_ARP_AGENT_URL")

    assert gateway == arp_bind, "arp-agent bind ünvanı şəbəkə gateway-i ilə eyni olmalıdır"
    assert agent_url == f"http://{arp_bind}:{arp_port}", "app EXAM_ARP_AGENT_URL agentin bind ünvanına getməlidir"
    import ipaddress

    assert ipaddress.ip_address(gateway) in ipaddress.ip_network(subnet)


def test_arp_agent_has_log_rotation_limits_and_healthcheck():
    compose = _compose()
    agent = compose["services"]["arp-agent"]
    assert (
        agent.get("logging") == compose["services"]["app"]["logging"]
    ), "P2-4: arp-agent logging anchor-suz (limitsiz log)"
    limits = agent["deploy"]["resources"]["limits"]
    assert _size_to_bytes(_interpolation_default(limits["memory"])) <= 128 * 1000**2
    assert float(_interpolation_default(limits["cpus"])) <= 0.5
    healthcheck = agent.get("healthcheck")
    assert healthcheck, "P2-4: arp-agent healthcheck yoxdur"
    probe = healthcheck["test"][1]
    # Agentin yeganə endpoint-i — bind uğursuzdursa bağlantı rədd olunur → unhealthy.
    assert "/mac?ip=" in probe
    assert "$${ARP_AGENT_BIND}" in probe and "$${ARP_AGENT_PORT}" in probe


# ── P2-9 — monitorinq izlədiyi sistemdən asılı olmamalıdır ─────────────────


def test_prometheus_does_not_depend_on_app_health():
    depends_on = _compose()["services"]["prometheus"].get("depends_on", {})
    assert "app" not in depends_on, "P2-9: prometheus.depends_on.app — app qalxmayanda monitorinq də qalxmır"


# ── P1-3 — Watchdog təkrar intervalı Alertmanager şablonuna ötürülür ───────


def _render_variables(command: str) -> set[str]:
    """`render-template.sh ŞABLON ÇIXIŞ VAR VAR ...` → {VAR, ...} (2026-09-14 P3-8)."""
    match = re.search(r"render-template\.sh\s+\S+\s+\S+\s+(.*?)\s*&&", command, flags=re.DOTALL)
    assert match, "render-template.sh çağırışı tapılmadı"
    return set(match.group(1).split())


def test_alertmanager_renders_watchdog_repeat_placeholder():
    alertmanager = _compose()["services"]["alertmanager"]
    assert "WATCHDOG_REPEAT" in alertmanager["environment"]
    command = " ".join(alertmanager["command"])
    variables = _render_variables(command)
    assert "WATCHDOG_REPEAT" in variables, "P1-3: __WATCHDOG_REPEAT__ əvəzləməsi yoxdur"
    template = (ROOT / "docker/alertmanager/alertmanager.tmpl.yml").read_text(encoding="utf-8")
    placeholders = {name.strip("_") for name in re.findall(r"__[A-Z_]+__", template)} - {"PLACEHOLDER"}
    assert placeholders <= variables, f"şablondakı placeholder-lar render olunmur: {placeholders - variables}"
    assert variables <= set(alertmanager["environment"]), "render dəyişənləri compose environment-də olmalıdır"


# ── 2026-09-14 infra auditi (wave 2): P3-3 Redis parolu argv-də deyil ──────


def test_redis_password_is_not_on_the_command_line_and_healthcheck_keeps_auth_env():
    redis = _compose()["services"]["redis"]
    command = " ".join(redis["command"])
    assert "requirepass" not in command and "REDIS_PASSWORD" not in command, "P3-3: parol argv-də olmamalıdır"
    assert redis["command"] == ["sh", "/etc/redis/entrypoint.sh"]
    # Şablon + entrypoint + ortaq render skripti mount olunur.
    binds = {volume.split(":")[0] for volume in redis["volumes"]}
    assert {"./docker/redis/redis.conf.tmpl", "./docker/redis/entrypoint.sh", "./docker/render-template.sh"} <= binds
    template = REDIS_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert re.search(r'^requirepass "__REDIS_PASSWORD__"$', template, flags=re.MULTILINE)
    # Healthcheck parolu yenə REDISCLI_AUTH-dan alır (argv-də yox).
    assert redis["healthcheck"]["test"] == ["CMD", "redis-cli", "ping"]
    assert "REDISCLI_AUTH" in redis["environment"] and "REDIS_PASSWORD" in redis["environment"]
    assert (ROOT / "docker/render-template.sh").exists()
    # Digər servislər eyni renderi işlədir (mount yolu fərqli ola bilər).
    for service in ("alertmanager", "blackbox_exporter"):
        volumes = " ".join(_compose()["services"][service]["volumes"])
        assert "./docker/render-template.sh:" in volumes, service


def test_redis_entrypoint_renders_secret_conf_and_hands_off_without_the_password(tmp_path):
    """Skript real `sh` ilə icra olunur; image entrypoint-i və `chown` stub-lanır."""
    if shutil.which("sh") is None:
        pytest.skip("sh yoxdur")
    conf_dir = tmp_path / "etc-redis"
    conf_dir.mkdir()
    shutil.copy(REDIS_TEMPLATE_PATH, conf_dir / "redis.conf.tmpl")
    shutil.copy(RENDER_TEMPLATE_PATH, conf_dir / "render-template.sh")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_entrypoint = fake_bin / "docker-entrypoint.sh"
    fake_entrypoint.write_text(
        "#!/bin/sh\nprintf 'ARGS:%s\\n' \"$*\"\nprintf 'ENV_PASSWORD:%s\\n' \"${REDIS_PASSWORD:-<unset>}\"\n",
        encoding="utf-8",
    )
    fake_entrypoint.chmod(0o755)
    rendered = tmp_path / "redis.conf"
    password = 'p|a&s/s\\w"o$rd'
    result = subprocess.run(
        ["sh", str(REDIS_ENTRYPOINT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "REDIS_PASSWORD": password,
            "REDIS_MAXMEMORY": "512mb",
            "REDIS_CONF_DIR": str(conf_dir),
            "REDIS_RENDERED_CONF": str(rendered),
        },
    )
    assert result.returncode == 0, result.stderr
    assert f"ARGS:redis-server {rendered}" in result.stdout, "argv yalnız konfiq faylı daşımalıdır"
    assert password not in result.stdout
    assert "ENV_PASSWORD:<unset>" in result.stdout, "sirr redis-server mühitindən silinməlidir"
    assert oct(rendered.stat().st_mode & 0o777) == "0o400"
    text = rendered.read_text(encoding="utf-8")
    # redis.conf ikiqat dırnaq qaydası: `\\` və `\"` qaçırılır, qalan simvollar hərfidir.
    assert 'requirepass "p|a&s/s\\\\w\\"o$rd"' in text
    assert "maxmemory 512mb" in text and "maxmemory-policy noeviction" in text


# ── P3-1 / P3-2 — nginx real dinləmə yoxlaması, app healthcheck şərhi ─────


def test_nginx_healthcheck_probes_stub_status_listener_instead_of_config_parse():
    nginx = _compose()["services"]["nginx"]
    test = nginx["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL" and "nginx -t" not in test[1], "P3-1: `nginx -t` dinləməni yoxlamır"
    assert "http://127.0.0.1:8081/stub_status" in test[1]
    conf = (ROOT / "docker/nginx/nginx.conf").read_text(encoding="utf-8")
    stub_server = conf[conf.index("listen 8081;") :]
    assert re.search(r"location = /stub_status \{\s*stub_status;", stub_server)
    # Port host-a publish olunmur.
    assert not any(":8081" in str(port) for port in nginx.get("ports", []))


def test_app_healthcheck_comment_matches_the_ping_endpoint_it_probes():
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    app_section = text[text.index("\n  app:\n") : text.index("\n  celery_worker:\n")]
    healthcheck_comment = app_section[: app_section.index("    healthcheck:")]
    healthcheck_comment = healthcheck_comment[healthcheck_comment.rfind("    # Real HTTP yoxlaması") :]
    assert "/ping/" in healthcheck_comment, "P3-2: şərh yoxlanan endpoint-i adlandırmalıdır"
    assert "# Real HTTP yoxlaması: /health/ DB-ni yoxlayır" not in healthcheck_comment, "P3-2: köhnə, yanlış şərh"
    assert "http://localhost:8000/ping/" in app_section


# ── P3-12 — Daphne proxy başlıqları ───────────────────────────────────────


def test_daphne_parses_proxy_headers_and_nginx_overwrites_them():
    entrypoint = (ROOT / "docker/prod-entrypoint.sh").read_text(encoding="utf-8")
    daphne_block = entrypoint[entrypoint.index("exec daphne") :]
    assert re.search(r"^\s+--proxy-headers \\$", daphne_block, flags=re.MULTILINE), "P3-12"
    # Daphne XFF-in İLK elementini götürür — nginx onu overwrite etməlidir (append yox).
    nginx = (ROOT / "docker/nginx/nginx.conf").read_text(encoding="utf-8")
    assert "$proxy_add_x_forwarded_for" not in nginx
    assert nginx.count("proxy_set_header X-Forwarded-For   $remote_addr;") >= 2
