"""Enerji kəsilməsi və yük altında dayanıqlıq (sahib 2026-10-07).

«Server resurslarını düzgün istifadə etsin, yüklənmədə çökməsin; elektrik kəsilib
server yenidən yananda sistem özü-özünü ayağa qaldırsın.» DB-siz qapılar:

1. compose: hər servisdə `cpu_shares` / `oom_score_adj` (env ilə override), prioritet sırası;
2. stack daxili dayanıqlıq: beat cədvəl qoruyucusu, Redis `aof-load-truncated`,
   Postgres fsync, nginx resolver;
3. host selfheal: boot converge + autoheal skriptləri (saxta `docker` ilə davranış),
   systemd vahidləri, deploy kilidi, `prod-host-maint` → selfheal, prod-audit sətirləri.
Sənəd: docs/ops/POWER_OUTAGE_RECOVERY.md
"""

from __future__ import annotations

import dbm
import json
import os
import re
import shelve
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
SELFHEAL = ROOT / "scripts/ops/selfheal"
CONVERGE = SELFHEAL / "emsarena-converge.sh"
AUTOHEAL = SELFHEAL / "emsarena-autoheal.sh"
INSTALL = SELFHEAL / "install.sh"
BEAT_START = ROOT / "docker/celery-beat/start.sh"
WORKFLOW = ROOT / ".github/workflows/prod-host-maint.yml"
REMOTE_DEPLOY = ROOT / "scripts/deploy/remote_deploy.sh"
SEED = ROOT / "scripts/deploy/seed_database.sh"
PROD_AUDIT = ROOT / "scripts/ops/prod_audit.sh"
DOC = ROOT / "docs/ops/POWER_OUTAGE_RECOVERY.md"
LOCK_PATH = "/run/emsarena/deploy.lock"

_DEFAULT_RE = re.compile(r"^\$\{(?P<var>[A-Z0-9_]+):-(?P<default>[^}]*)\}$")

MONITORING = {
    "prometheus",
    "grafana",
    "loki",
    "promtail",
    "cadvisor",
    "alertmanager",
    "blackbox_exporter",
    "postgres_exporter",
    "node_exporter",
    "redis_exporter",
    "nginx_exporter",
    "pgbouncer_exporter",
    "docker-socket-proxy",
}
# servis → (cpu_shares, oom_score_adj) defoltları (sahibin cədvəli + arp-agent).
EXPECTED = {
    "postgres": (4096, -900),
    "pgbouncer": (2048, -800),
    "redis": (2048, -700),
    "nginx": (2048, -500),
    "arp-agent": (1024, -500),
    "app": (1024, 0),
    "celery_worker": (768, 100),
    "celery_worker_heavy": (256, 300),
    "celery_beat": (512, 0),
    "postgres-backup": (256, 200),
    "piston": (256, 400),
    **{name: (256, 500) for name in MONITORING},
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _services() -> dict:
    return yaml.safe_load(_read(COMPOSE_PATH))["services"]


def _default(value) -> tuple[str, int]:
    match = _DEFAULT_RE.match(str(value).strip())
    assert match, f"`${{VAR:-default}}` formasında deyil: {value!r}"
    return match.group("var"), int(match.group("default"))


def _priority(name: str) -> tuple[int, int]:
    svc = _services()[name]
    return _default(svc["cpu_shares"])[1], _default(svc["oom_score_adj"])[1]


# ── 1. Resurs prioriteti ────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(_services()))
def test_every_service_declares_env_overridable_cpu_shares_and_oom_score_adj(name):
    svc = _services()[name]
    assert "cpu_shares" in svc and "oom_score_adj" in svc, f"{name}: prioritet açarları yoxdur (bax compose başlığı)"
    shares_var, shares = _default(svc["cpu_shares"])
    oom_var, oom = _default(svc["oom_score_adj"])
    assert shares_var.endswith("_CPU_SHARES") and oom_var.endswith("_OOM_SCORE_ADJ")
    assert 2 <= shares <= 262144
    assert -1000 <= oom <= 1000
    if name in EXPECTED:
        assert (shares, oom) == EXPECTED[name], name


def test_known_service_inventory_is_classified():
    """Yeni servis prioritet cədvəlinə düşməlidir (monitorinq/fon/kritik)."""
    unknown = set(_services()) - set(EXPECTED)
    assert not unknown, f"prioritet sinfi təyin edilməyib: {sorted(unknown)} — EXPECTED-ə əlavə edin"


def test_priority_ordering_protects_the_request_path():
    pg_cpu, pg_oom = _priority("postgres")
    pgb_cpu, pgb_oom = _priority("pgbouncer")
    rd_cpu, rd_oom = _priority("redis")
    ngx_cpu, ngx_oom = _priority("nginx")
    app_cpu, app_oom = _priority("app")
    cw_cpu, cw_oom = _priority("celery_worker")
    beat_cpu, _ = _priority("celery_beat")
    heavy_cpu, heavy_oom = _priority("celery_worker_heavy")
    # OOM-killer: postgres < redis < app < monitorinq (sahibin tələbi), aradakılar da sıralı.
    assert pg_oom < pgb_oom < rd_oom < ngx_oom < app_oom < cw_oom < heavy_oom
    for name in MONITORING:
        cpu, oom = _priority(name)
        assert oom > app_oom > rd_oom > pg_oom, name
        assert oom > heavy_oom, name
        assert cpu < app_cpu, name
    # CPU rəqabəti: DB > hovuz/Redis/nginx > app > worker > beat > heavy.
    assert pg_cpu > max(pgb_cpu, rd_cpu, ngx_cpu)
    assert min(pgb_cpu, rd_cpu, ngx_cpu) > app_cpu > cw_cpu > beat_cpu > heavy_cpu
    assert _priority("postgres-backup")[0] <= heavy_cpu


@pytest.mark.parametrize("name", sorted(_services()))
def test_priority_keys_do_not_conflict_with_deploy_limits_or_hardening(name):
    svc = _services()[name]
    limits = (svc.get("deploy") or {}).get("resources", {}).get("limits", {})
    assert limits.get("memory"), f"{name}: deploy.resources.limits.memory yoxdur"
    # Servis səviyyəli `cpus`/`mem_limit` deploy.resources.limits ilə toqquşur (compose xətası).
    for key in ("cpus", "mem_limit", "memswap_limit", "cpu_quota", "cpu_count", "cpu_percent"):
        assert key not in svc, f"{name}: `{key}` deploy.resources.limits ilə toqquşur"
    if not svc.get("privileged"):
        assert "no-new-privileges:true" in svc.get("security_opt", []), name


def test_compose_header_explains_that_shares_only_matter_under_contention():
    text = _read(COMPOSE_PATH)
    header = text[: text.index("\nservices:\n")]
    assert "cpu_shares" in header and "oom_score_adj" in header
    assert "RƏQABƏT" in header and "OOM-killer" in header
    assert "Postgres/Redis" in header


def _docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _docker_compose_available(), reason="docker compose yoxdur")
def test_docker_compose_accepts_the_priority_keys_and_env_overrides(tmp_path):
    """Real compose-spec yoxlaması: `${X:--900}` tam ədədə çevrilir, override işləyir."""
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COMPOSE_") and not key.endswith(("_CPU_SHARES", "_OOM_SCORE_ADJ"))
    }
    env |= {
        "REDIS_PASSWORD": "dummy",
        "GRAFANA_ADMIN_PASSWORD": "dummy",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "POSTGRES_DB": "d",
        "COMPOSE_PROFILES": "coding",
        "POSTGRES_OOM_SCORE_ADJ": "-950",
    }
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(empty_env), "-f", str(COMPOSE_PATH), "config", "--format", "json"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    services = json.loads(result.stdout)["services"]
    assert services["postgres"]["oom_score_adj"] == -950, "env override işləmir"
    assert services["postgres"]["cpu_shares"] == 4096
    for name, (shares, oom) in EXPECTED.items():
        if name == "postgres":
            continue
        assert services[name]["cpu_shares"] == shares, name
        # compose 0-ı (defolt) JSON-da buraxır.
        assert services[name].get("oom_score_adj", 0) == oom, name


# ── 2. Stack daxili dayanıqlıq ─────────────────────────────────────────────


def test_celery_beat_command_runs_the_corrupt_schedule_guard_from_a_bind_mount():
    beat = _services()["celery_beat"]
    command = beat["command"]
    assert command[:2] == ["sh", "/opt/emsarena/celery-beat-start.sh"], "beat qoruyucu sarğı ilə başlamalıdır"
    assert command[2:6] == ["celery", "-A", "config", "beat"]
    assert command[command.index("--schedule") + 1] == "/tmp/celerybeat-schedule"
    assert "./docker/celery-beat/start.sh:/opt/emsarena/celery-beat-start.sh:ro" in beat["volumes"]
    # Healthcheck eyni fayla baxır (dəyişməyib).
    assert "celerybeat-schedule*" in beat["healthcheck"]["test"][1]
    script = _read(BEAT_START)
    assert 'shelve.open(sys.argv[1], flag="r")' in script
    assert 'rm -f "$schedule"' in script
    assert script.rstrip().endswith('exec "$@"')
    assert "<<" not in "\n".join(str(item) for item in command), "compose-da heredoc yoxdur"


def _run_beat_guard(tmp_path: Path, schedule: Path) -> subprocess.CompletedProcess:
    marker = tmp_path / "exec-marker"
    return subprocess.run(
        [
            "sh",
            str(BEAT_START),
            "sh",
            "-c",
            f'echo "$@" > "{marker}"',
            "beat-stub",
            "celery",
            "--schedule",
            str(schedule),
        ],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHON_BIN": sys.executable},
        timeout=60,
        check=False,
    )


def _schedule_files(schedule: Path) -> list[Path]:
    return sorted(p for p in schedule.parent.iterdir() if p.name.startswith(schedule.name))


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yoxdur")
def test_beat_guard_removes_an_unreadable_schedule_and_still_execs_beat(tmp_path):
    schedule = tmp_path / "celerybeat-schedule"
    schedule.write_bytes(b"\x00\x01garbage-after-power-loss")
    result = _run_beat_guard(tmp_path, schedule)
    assert result.returncode == 0, result.stderr
    assert "korlanıb" in result.stderr
    assert not _schedule_files(schedule), "korlanmış fayl silinməlidir"
    assert (tmp_path / "exec-marker").read_text(encoding="utf-8").strip() == f"celery --schedule {schedule}"


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yoxdur")
def test_beat_guard_removes_a_readable_db_with_a_corrupt_pickle(tmp_path):
    """Celery-nin özü tutmadığı hal: DB açılır, `entries` pickle-ı pozulub → crash-loop idi."""
    schedule = tmp_path / "celerybeat-schedule"
    with dbm.open(str(schedule), "c") as db:
        db[b"entries"] = b"\x80\x04\x95truncated"
    result = _run_beat_guard(tmp_path, schedule)
    assert result.returncode == 0, result.stderr
    assert "schedule check failed" in result.stderr
    assert not _schedule_files(schedule)


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh yoxdur")
def test_beat_guard_keeps_a_healthy_schedule_and_tolerates_a_missing_one(tmp_path):
    schedule = tmp_path / "celerybeat-schedule"
    with shelve.open(str(schedule)) as db:
        db["entries"] = {"sweep": {"last_run_at": None}}
        db["__version__"] = "5.4"
    before = _schedule_files(schedule)
    result = _run_beat_guard(tmp_path, schedule)
    assert result.returncode == 0, result.stderr
    assert _schedule_files(schedule) == before, "sağlam cədvəl silinməməlidir"

    missing = tmp_path / "fresh" / "celerybeat-schedule"
    missing.parent.mkdir()
    result = _run_beat_guard(tmp_path, missing)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "exec-marker").exists()


def test_redis_aof_tolerates_a_truncated_tail_after_power_loss():
    template = _read(ROOT / "docker/redis/redis.conf.tmpl")
    assert re.search(r"^appendonly yes$", template, flags=re.MULTILINE)
    assert re.search(r"^aof-load-truncated yes$", template, flags=re.MULTILINE)
    assert not re.search(r"^aof-load-truncated no", template, flags=re.MULTILINE)


def test_postgres_durability_settings_are_never_disabled():
    command = " ".join(str(item) for item in _services()["postgres"]["command"])
    for setting in ("fsync", "full_page_writes", "synchronous_commit"):
        assert not re.search(rf"\b{setting}\s*=\s*(off|false|0)\b", command, flags=re.IGNORECASE), setting
    for path in (ROOT / "docker/postgres-init").rglob("*"):
        if path.is_file():
            assert not re.search(r"\bfsync\s*=\s*off", _read(path), flags=re.IGNORECASE), path
    text = _read(COMPOSE_PATH)
    assert "fsync / full_page_writes / synchronous_commit" in text, "postgres-də qeyd yoxdur"


def test_nginx_resolves_the_app_upstream_at_request_time():
    """Boot-da app hələ yoxdursa nginx yenə qalxır (502 → öz-özünə düzəlir) — dəyişiklik lazım deyil."""
    conf = _read(ROOT / "docker/nginx/nginx.conf")
    assert re.search(r"^resolver 127\.0\.0\.11 ", conf, flags=re.MULTILINE)
    assert "set $emsarena_app http://app:8000;" in conf
    proxy_targets = re.findall(r"proxy_pass\s+([^;]+);", conf)
    assert proxy_targets and set(proxy_targets) == {"$emsarena_app"}


# ── 3. Host selfheal skriptləri ────────────────────────────────────────────

SHELL_SCRIPTS = sorted(SELFHEAL.glob("*.sh"))


def test_selfheal_ships_the_expected_files():
    names = {path.name for path in SELFHEAL.iterdir()}
    assert {
        "emsarena-converge.sh",
        "emsarena-autoheal.sh",
        "install.sh",
        "emsarena-converge.service",
        "emsarena-autoheal.service",
        "emsarena-autoheal.timer",
    } <= names


@pytest.mark.parametrize("path", SHELL_SCRIPTS + [REMOTE_DEPLOY, SEED, PROD_AUDIT], ids=lambda p: p.name)
def test_shell_scripts_parse(path):
    if shutil.which("bash") is None:
        pytest.skip("bash yoxdur")
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("path", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_selfheal_scripts_are_strict_and_pinned_to_bash(path):
    text = _read(path)
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "\nset -euo pipefail\n" in text
    assert "set -x" not in text, "xtrace sirri jurnala çıxara bilər"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck yoxdur")
@pytest.mark.parametrize("path", SHELL_SCRIPTS + [BEAT_START], ids=lambda p: p.name)
def test_selfheal_scripts_are_shellcheck_clean(path):
    result = subprocess.run(["shellcheck", str(path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout


def test_beat_guard_parses_with_posix_sh():
    if shutil.which("sh") is None:
        pytest.skip("sh yoxdur")
    result = subprocess.run(["sh", "-n", str(BEAT_START)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_scripts_never_print_compose_config_or_read_the_env_file_as_shell():
    for path in (CONVERGE, AUTOHEAL, INSTALL):
        code = "\n".join(line for line in _read(path).splitlines() if not line.lstrip().startswith("#"))
        for match in re.finditer(r"compose[^\n]*\bconfig\b[^\n]*", code):
            assert "-q" in match.group(0), f"{path.name}: `compose config` -q olmadan sirləri çap edir"
        assert not re.search(r"(^|\s)(\.|source)\s+[^\n]*\.env\b", code), f"{path.name}: .env shell kimi oxunur"
        assert "cat .env" not in code and "printenv" not in code


def test_autoheal_only_touches_this_compose_project():
    text = _read(AUTOHEAL)
    assert '--filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"' in text
    assert "com.docker.compose.project.working_dir" in text
    assert "com.docker.compose.oneoff" in text
    assert "flock -n 9" in text
    assert 'AUTOHEAL_MAX_RESTARTS_PER_HOUR:-}" 3' in text and "3600" in text
    assert "postgres redis postgres-backup" in text


def test_converge_uses_the_deploy_command_without_building_or_pulling():
    text = _read(CONVERGE)
    assert "up -d --no-build" in text and "--pull never" in text
    assert '--scale "app=${app_replicas}"' in text and '--scale "celery_worker=${celery_replicas}"' in text
    assert "export RUN_RELEASE_ON_START=false" in text
    assert "--remove-orphans" not in "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert '"${APP_IMAGE_REPOSITORY}:latest"' in text
    assert "CONVERGE_TIMEOUT_SECONDS:-600" in text


def test_systemd_units_match_the_boot_contract():
    converge = _read(SELFHEAL / "emsarena-converge.service")
    assert "Type=oneshot" in converge
    assert "After=docker.service network-online.target" in converge
    assert re.search(r"^Wants=network-online\.target", converge, flags=re.MULTILINE)
    assert "WantedBy=multi-user.target" in converge
    assert "ExecStart=/usr/local/sbin/emsarena-converge.sh" in converge
    assert "User=@RUN_AS@" in converge
    timer = _read(SELFHEAL / "emsarena-autoheal.timer")
    assert "OnUnitActiveSec=2min" in timer and "WantedBy=timers.target" in timer
    service = _read(SELFHEAL / "emsarena-autoheal.service")
    assert "ExecStart=/usr/local/sbin/emsarena-autoheal.sh" in service and "Type=oneshot" in service
    install = _read(INSTALL)
    assert "s|@RUN_AS@|${RUN_AS}|g" in install
    assert "systemctl enable emsarena-converge.service" in install
    assert "systemctl enable --now emsarena-autoheal.timer" in install
    assert "RUN_DIR=/run/emsarena" in install and "/etc/tmpfiles.d/emsarena.conf" in install
    assert "DEPLOY_LOCK_FILE=${RUN_DIR}/deploy.lock" in install
    assert "--check" in install and "--dry-run" in install


def test_every_writer_uses_the_same_deploy_lock():
    for path in (CONVERGE, AUTOHEAL, REMOTE_DEPLOY, SEED):
        assert f'DEPLOY_LOCK_FILE="${{DEPLOY_LOCK_FILE:-{LOCK_PATH}}}"' in _read(path), path.name
    deploy = _read(REMOTE_DEPLOY)
    assert 'flock -w "$DEPLOY_LOCK_WAIT_SECONDS" 9' in deploy
    dispatch = deploy[deploy.index('case "$DEPLOY_MODE" in\n  docker)') :]
    assert dispatch.index("acquire_deploy_lock") < dispatch.index("docker_deploy")


# ── saxta docker ilə davranış ───────────────────────────────────────────────

_FAKE_DOCKER = r"""#!/bin/bash
# Testlər üçün saxta docker: $FAKE_DIR/containers fiksturundan cavab verir.
echo "APP_IMAGE=${APP_IMAGE:-} RUN_RELEASE_ON_START=${RUN_RELEASE_ON_START:-} $*" >>"$FAKE_DIR/calls.log"
case "$1" in
  info) exit 0 ;;
  ps)
    proj=""
    for a in "$@"; do case "$a" in label=com.docker.compose.project=*) proj="${a#label=com.docker.compose.project=}" ;; esac; done
    awk -F'|' -v p="$proj" '$1 == p {print $2}' "$FAKE_DIR/containers"
    ;;
  inspect)
    fmt="$3"; shift 3
    for id in "$@"; do
      case "$fmt" in
        # autoheal: id|ad|status|... (fiksturun 1-ci sahəsi — layihə — atılır)
        "{{.Id}}|"*) awk -F'|' -v i="$id" '$2 == i {sub(/^[^|]*\|/, ""); print}' "$FAKE_DIR/containers" ;;
        # converge image seçimi: servis|oneoff|teq|image-id
        "{{index "*) [ -f "$FAKE_DIR/converge_rows" ] && awk -F'|' -v i="$id" '$1 == i {sub(/^[^|]*\|/, ""); print}' "$FAKE_DIR/converge_rows" ;;
        # converge yekun hesabatı: ad status oneoff
        "{{.Name}} "*) awk -F'|' -v i="$id" '$2 == i {print $3, $4, $10}' "$FAKE_DIR/containers" ;;
      esac
    done
    ;;
  image)
    ref="${*: -1}"
    if [ "$ref" = "emsarena-prod:latest" ]; then
      [ -s "$FAKE_DIR/latest_id" ] || exit 1
      cat "$FAKE_DIR/latest_id"
    else
      grep -qx "$ref" "$FAKE_DIR/local_images" 2>/dev/null || exit 1
      echo "sha256:local"
    fi
    ;;
  compose)
    case "$*" in
      "compose version") exit 0 ;;
      "compose up --help") echo "      --pull string   Pull image before running" ;;
      *" config -q") exit 0 ;;
      *" up "*)
        n=$(cat "$FAKE_DIR/up_count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" >"$FAKE_DIR/up_count"
        [ "$n" -le "${FAKE_UP_FAIL_TIMES:-0}" ] && exit 1
        exit 0
        ;;
    esac
    ;;
  restart | start) exit "${FAKE_ACTION_RC:-0}" ;;
esac
exit 0
"""

_FAKE_FLOCK = '#!/bin/bash\nexit "${FAKE_FLOCK_RC:-0}"\n'


@pytest.fixture
def fake_host(tmp_path):
    if shutil.which("bash") is None:
        pytest.skip("bash yoxdur")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name, body in (("docker", _FAKE_DOCKER), ("flock", _FAKE_FLOCK)):
        path = fake_bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
    (app_dir / ".env").write_text("APP_REPLICAS=8\nCELERY_REPLICAS=2\nSECRET_KEY=topsecret-value\n", encoding="utf-8")
    (tmp_path / "loadavg").write_text("0.50 0.40 0.30 1/100 1\n", encoding="utf-8")
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_DIR": str(tmp_path),
        "SELFHEAL_CONF": str(tmp_path / "no-such-conf"),
        "APP_DIR": str(app_dir),
        "COMPOSE_PROJECT": "proj",
        "DEPLOY_LOCK_FILE": str(run_dir / "deploy.lock"),
        "AUTOHEAL_STATE_DIR": str(run_dir / "autoheal"),
        "AUTOHEAL_PAUSE_FILE": str(run_dir / "autoheal.pause"),
        "AUTOHEAL_LOADAVG_FILE": str(tmp_path / "loadavg"),
        "CONVERGE_SETTLE_SECONDS": "0",
        "CONVERGE_RETRY_SECONDS": "0",
        "CONVERGE_TIMEOUT_SECONDS": "60",
    }
    return tmp_path, env


def _containers(tmp_path: Path, rows: list[str]) -> None:
    (tmp_path / "containers").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _run(script: Path, env: dict, *args: str, **extra: str) -> subprocess.CompletedProcess:
    full = dict(env)
    full.update(extra)
    return subprocess.run(
        ["bash", str(script), *args], capture_output=True, text=True, env=full, timeout=120, check=False
    )


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _actions(tmp_path: Path) -> list[str]:
    return [line.split(" ", 2)[2] for line in _calls(tmp_path) if re.search(r" (restart|start) ", line)]


# project|id|ad|status|health|restart|kod|oom|servis|oneoff|working_dir|teq|image-id|stop_timeout|xəta
def _row(
    cid,
    name,
    status,
    health,
    service,
    *,
    code=0,
    policy="unless-stopped",
    oom="false",
    oneoff="False",
    workdir="APPDIR",
    image="postgres:16-alpine",
    image_id="sha256:pg",
    stop="",
    error="",
    project="proj",
):
    return "|".join(
        [
            project,
            cid,
            f"/{name}",
            status,
            health,
            policy,
            str(code),
            oom,
            service,
            oneoff,
            workdir,
            image,
            image_id,
            stop,
            error,
        ]
    )


def _healthy_core(app_dir):
    return [
        _row("pg1", "proj-postgres", "running", "healthy", "postgres", workdir=app_dir),
        _row("rd1", "proj-redis", "running", "healthy", "redis", workdir=app_dir, image="redis:7-alpine"),
    ]


def test_autoheal_restarts_and_starts_only_eligible_project_containers_with_limits(fake_host):
    tmp_path, env = fake_host
    app_dir = env["APP_DIR"]
    good = dict(image="emsarena-prod:abc", image_id="sha256:good", workdir=app_dir)
    (tmp_path / "latest_id").write_text("sha256:good\n", encoding="utf-8")
    _containers(
        tmp_path,
        _healthy_core(app_dir)
        + [
            _row("app1", "proj-app-1", "running", "unhealthy", "app", stop="130", **good),
            _row("app2", "proj-app-2", "running", "unhealthy", "app", **good),
            _row("wk1", "proj-celery_worker-1", "exited", "none", "celery_worker", code=1, **good),
            _row("bt1", "proj-celery-beat", "exited", "healthy", "celery_beat", code=0, **good),
            _row(
                "ng1",
                "proj-nginx",
                "exited",
                "none",
                "nginx",
                code=128,
                workdir=app_dir,
                image="nginx:1.27",
                error="driver failed programming external connectivity",
            ),
            _row("one1", "proj-app-run-1", "exited", "none", "app", code=1, oneoff="True", policy="no", **good),
            _row("for1", "other-app-1", "exited", "none", "app", code=1, project="other", **good),
            _row(
                "fw1",
                "proj-x-1",
                "exited",
                "none",
                "app",
                code=1,
                image="emsarena-prod:abc",
                image_id="sha256:good",
                workdir="/srv/elsewhere",
            ),
            _row(
                "new1",
                "proj-heavy-1",
                "created",
                "none",
                "celery_worker_heavy",
                image="emsarena-prod:new",
                image_id="sha256:untested",
                workdir=app_dir,
            ),
        ],
    )

    first = _run(AUTOHEAL, env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert _actions(tmp_path) == ["start wk1", "start ng1"], "yalnız start xətalı/çökmüş konteynerlər"
    assert "unhealthy (1/3): proj-app-1" in first.stdout
    assert "HOLD: proj-heavy-1 sonuncu SAĞLAM release olmayan" in first.stdout
    assert "proj-x-1 başqa qovluğun" in first.stdout
    assert "proj-celery-beat səliqəli dayandırılıb" in first.stdout

    _run(AUTOHEAL, env)
    third = _run(AUTOHEAL, env)
    assert third.returncode == 0, third.stdout + third.stderr
    actions = _actions(tmp_path)
    assert "restart -t 120 app1" in actions, "3-cü ardıcıl unhealthy → restart (stop_timeout 130 → tavan 120)"
    assert "restart -t 10 app2" not in actions, "eyni servisdən bir keçiddə yalnız bir restart"
    assert actions.count("start wk1") == 3

    fourth = _run(AUTOHEAL, env)
    assert fourth.returncode == 0, fourth.stdout + fourth.stderr
    actions = _actions(tmp_path)
    assert actions.count("start wk1") == 3, "saatda 3-dən çox əməliyyat olmaz"
    assert "restart -t 10 app2" in actions, "app2 növbəti keçiddə (rolling)"
    log = (tmp_path / "run/autoheal/actions.log").read_text(encoding="utf-8")
    assert "LIMIT: proj-celery_worker-1" in log and "ACTION: restart proj-app-1" in log

    touched = " ".join(_actions(tmp_path))
    for untouched in ("bt1", "one1", "for1", "fw1", "new1", "pg1", "rd1"):
        assert untouched not in touched, untouched


def test_autoheal_never_restarts_stateful_services_and_waits_for_a_sick_core(fake_host):
    tmp_path, env = fake_host
    app_dir = env["APP_DIR"]
    (tmp_path / "latest_id").write_text("sha256:good\n", encoding="utf-8")
    _containers(
        tmp_path,
        [
            _row("pg1", "proj-postgres", "running", "unhealthy", "postgres", workdir=app_dir),
            _row("rd1", "proj-redis", "running", "healthy", "redis", workdir=app_dir),
            _row(
                "app1",
                "proj-app-1",
                "running",
                "unhealthy",
                "app",
                image="emsarena-prod:abc",
                image_id="sha256:good",
                workdir=app_dir,
            ),
        ],
    )
    output = ""
    for _ in range(4):
        result = _run(AUTOHEAL, env)
        assert result.returncode == 0, result.stdout + result.stderr
        output += result.stdout
    assert _actions(tmp_path) == [], "postgres unhealthy-yə görə restart olunmur; app səbəb düzələnə qədər gözləyir"
    assert output.count("HOLD: proj-postgres (postgres) unhealthy, amma vəziyyətli servisdir") == 1, "bir dəfə yazılır"
    assert "HOLD: proj-app-1 unhealthy, amma əsas servislər sağlam deyil (postgres:running/unhealthy)" in output


def test_autoheal_skips_under_deploy_lock_pause_and_overload(fake_host):
    tmp_path, env = fake_host
    app_dir = env["APP_DIR"]
    (tmp_path / "latest_id").write_text("sha256:good\n", encoding="utf-8")
    _containers(
        tmp_path,
        _healthy_core(app_dir)
        + [
            _row(
                "app1",
                "proj-app-1",
                "running",
                "unhealthy",
                "app",
                image="emsarena-prod:abc",
                image_id="sha256:good",
                workdir=app_dir,
            ),
            _row(
                "wk1",
                "proj-celery_worker-1",
                "exited",
                "none",
                "celery_worker",
                code=2,
                image="emsarena-prod:abc",
                image_id="sha256:good",
                workdir=app_dir,
            ),
        ],
    )
    locked = _run(AUTOHEAL, env, FAKE_FLOCK_RC="1")
    assert locked.returncode == 0 and "SKIP: deploy/converge gedir" in locked.stdout
    assert _calls(tmp_path) == [], "deploy gedəndə docker-ə heç bir çağırış olmamalıdır"

    pause = Path(env["AUTOHEAL_PAUSE_FILE"])
    pause.write_text("", encoding="utf-8")
    paused = _run(AUTOHEAL, env)
    assert "PAUSE:" in paused.stdout and _calls(tmp_path) == []
    pause.unlink()

    (tmp_path / "loadavg").write_text("999.0 50.0 40.0 1/100 1\n", encoding="utf-8")
    for _ in range(3):
        busy = _run(AUTOHEAL, env)
        assert busy.returncode == 0, busy.stdout + busy.stderr
    assert "OVERLOAD" in busy.stdout
    assert _actions(tmp_path) == ["start wk1"] * 3, "yük altında yalnız start; unhealthy restart yoxdur"

    dry_env = dict(env)
    (tmp_path / "loadavg").write_text("0.1 0.1 0.1 1/100 1\n", encoding="utf-8")
    shutil.rmtree(tmp_path / "run/autoheal")
    (tmp_path / "calls.log").unlink()
    dry = _run(AUTOHEAL, dry_env, "--dry-run")
    assert dry.returncode == 0 and "DRY-RUN: start proj-celery_worker-1" in dry.stdout
    assert _actions(tmp_path) == []


def _converge_rows(tmp_path: Path, rows: list[str]) -> None:
    # id|servis|oneoff|teq|image-id  (fake inspect id-ni atır)
    (tmp_path / "converge_rows").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _up_calls(tmp_path: Path) -> list[str]:
    return [line for line in _calls(tmp_path) if " compose -f docker-compose.prod.yml up " in line]


def _converge_fixture(tmp_path: Path, app_dir: str, ref: str, image_id: str) -> None:
    _containers(tmp_path, [_row("a1", "proj-app-1", "running", "healthy", "app", workdir=app_dir)])
    _converge_rows(tmp_path, [f"a1|app|False|{ref}|{image_id}", f"b1|celery_beat|False|{ref}|{image_id}"])
    with (tmp_path / "containers").open("a", encoding="utf-8") as handle:
        handle.write(_row("b1", "proj-celery-beat", "running", "healthy", "celery_beat", workdir=app_dir) + "\n")


def test_converge_keeps_the_running_tag_when_it_is_the_last_healthy_release(fake_host):
    tmp_path, env = fake_host
    (tmp_path / "latest_id").write_text("sha256:good\n", encoding="utf-8")
    _converge_fixture(tmp_path, env["APP_DIR"], "emsarena-prod:abc1234", "sha256:good")
    result = _run(CONVERGE, env)
    assert result.returncode == 0, result.stdout + result.stderr
    ups = _up_calls(tmp_path)
    assert len(ups) == 1
    assert ups[0].startswith("APP_IMAGE=emsarena-prod:abc1234 RUN_RELEASE_ON_START=false ")
    assert "up -d --no-build --pull never --scale app=8 --scale celery_worker=2" in ups[0]
    assert "--remove-orphans" not in ups[0] and "build" not in ups[0].replace("--no-build", "")
    assert "topsecret" not in result.stdout + result.stderr, "sirr çap olunmamalıdır"


def test_converge_falls_back_to_latest_when_containers_run_an_unpromoted_image(fake_host):
    tmp_path, env = fake_host
    (tmp_path / "latest_id").write_text("sha256:good\n", encoding="utf-8")
    _converge_fixture(tmp_path, env["APP_DIR"], "emsarena-prod:new9999", "sha256:untested")
    result = _run(CONVERGE, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _up_calls(tmp_path)[0].startswith("APP_IMAGE=emsarena-prod:latest ")
    assert "yarımçıq deploy" in result.stdout


def test_converge_without_latest_keeps_only_an_existing_running_tag_or_refuses(fake_host):
    tmp_path, env = fake_host
    _converge_fixture(tmp_path, env["APP_DIR"], "emsarena-prod:abc1234", "sha256:x")
    (tmp_path / "local_images").write_text("emsarena-prod:abc1234\n", encoding="utf-8")
    result = _run(CONVERGE, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _up_calls(tmp_path)[0].startswith("APP_IMAGE=emsarena-prod:abc1234 ")

    (tmp_path / "local_images").unlink()
    (tmp_path / "calls.log").unlink()
    refused = _run(CONVERGE, env)
    assert refused.returncode != 0
    assert _up_calls(tmp_path) == [], "test olunmamış image start edilməməlidir"
    assert "start EDİLMİR" in refused.stdout


def test_converge_retries_steps_aside_for_a_deploy_and_has_a_dry_check(fake_host):
    tmp_path, env = fake_host
    (tmp_path / "latest_id").write_text("sha256:good\n", encoding="utf-8")
    _converge_fixture(tmp_path, env["APP_DIR"], "emsarena-prod:abc1234", "sha256:good")

    retried = _run(CONVERGE, env, FAKE_UP_FAIL_TIMES="1")
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert len(_up_calls(tmp_path)) == 2 and "cəhd 1 uğursuz" in retried.stdout

    (tmp_path / "calls.log").unlink()
    deploying = _run(CONVERGE, env, FAKE_FLOCK_RC="1")
    assert deploying.returncode == 0 and _up_calls(tmp_path) == []
    assert "deploy stack-ı özü qaldırır" in deploying.stdout

    check = _run(CONVERGE, env, "--check")
    assert check.returncode == 0, check.stdout + check.stderr
    assert _up_calls(tmp_path) == []
    assert any(line.endswith("compose -f docker-compose.prod.yml config -q") for line in _calls(tmp_path))


def _deploy_lock_function() -> str:
    match = re.search(r"^acquire_deploy_lock\(\) \{\n.*?^\}\n", _read(REMOTE_DEPLOY), flags=re.MULTILINE | re.DOTALL)
    assert match
    return match.group(0)


def test_deploy_lock_is_optional_infrastructure_but_fails_closed_when_held(fake_host):
    tmp_path, env = fake_host
    harness = (
        f"set -euo pipefail\n{_deploy_lock_function()}\nDEPLOY_LOCK_WAIT_SECONDS=1\nacquire_deploy_lock\necho LOCKED\n"
    )
    missing = subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={**env, "DEPLOY_LOCK_FILE": str(tmp_path / "absent/deploy.lock")},
    )
    assert missing.returncode == 0 and "LOCKED" in missing.stdout and "continuing without the lock" in missing.stderr

    held = subprocess.run(
        ["bash", "-c", harness], capture_output=True, text=True, check=False, env={**env, "FAKE_FLOCK_RC": "1"}
    )
    assert held.returncode == 1 and "LOCKED" not in held.stdout
    acquired = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=False, env=env)
    assert acquired.returncode == 0 and "LOCKED" in acquired.stdout
    assert (tmp_path / "run/deploy.lock").exists()


# ── 4. Workflow + audit + sənəd ────────────────────────────────────────────


def _workflow() -> dict:
    return yaml.safe_load(_read(WORKFLOW))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["host"]["steps"]


def test_prod_host_maint_offers_selfheal_and_selfheal_off():
    on = _workflow().get(True, _workflow().get("on"))
    options = on["workflow_dispatch"]["inputs"]["action"]["options"]
    assert "selfheal" in options and "selfheal-off" in options
    selfheal = [step for step in _steps() if "== 'selfheal'" in str(step.get("if", ""))]
    checkout = [step for step in selfheal if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert checkout and checkout[0]["with"]["persist-credentials"] is False
    runs = [step["run"] for step in selfheal if "run" in step]
    assert len(runs) == 1
    assert 'host bash "$SRC/install.sh" --app-dir "$APP_DIR" --source "$SRC"' in runs[0]
    assert 'SRC="$GITHUB_WORKSPACE/scripts/ops/selfheal"' in runs[0]
    off = [step["run"] for step in _steps() if "== 'selfheal-off'" in str(step.get("if", ""))]
    assert off and "disable --now emsarena-autoheal.timer" in off[0]


def test_selfheal_steps_do_not_echo_secrets():
    for step in _steps():
        if "selfheal" not in str(step.get("if", "")) or "run" not in step:
            continue
        script = step["run"]
        code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
        assert "secrets." not in code
        assert ".env" not in code, "selfheal addımı .env-ə toxunmamalıdır"
        for needle in ("printenv", "set -x", "env |", "docker compose config", "docker inspect"):
            assert needle not in code, needle
    install = _read(INSTALL)
    code = "\n".join(line for line in install.splitlines() if not line.lstrip().startswith("#"))
    assert re.findall(r"\.env\b", code) == [".env"], "install.sh .env-dən yalnız sahibini (stat) oxuyur"
    assert 'stat -c %U "${APP_DIR}/.env"' in code


def test_status_reports_selfheal_units_and_recent_autoheal_actions():
    status = _steps()[0]["run"]
    assert "emsarena-converge.service emsarena-autoheal.timer" in status
    assert "systemctl is-enabled" in status and "is-active emsarena-autoheal.timer" in status
    assert "journalctl -u emsarena-autoheal.service" in status
    assert "journalctl -u emsarena-converge.service -b" in status


def test_prod_audit_checks_selfheal_priority_docker_and_runner():
    text = _read(PROD_AUDIT)
    section = text[text.index('section "12. Enerji kəsilməsi') : text.index('section "Yekun"')]
    for needle in (
        "unit_enabled docker.service",
        "actions.runner*",
        "{{.LiveRestoreEnabled}}",
        "emsarena-converge.service",
        "emsarena-autoheal.timer",
        "{{.HostConfig.OomScoreAdj}} {{.HostConfig.CpuShares}}",
        "/oom_score_adj",
        "ps -q postgres",
        "ps -q app",
    ):
        assert needle in section, needle
    assert "ok " in section and "warn " in section


def test_power_outage_doc_covers_owner_actions():
    doc = _read(DOC)
    for needle in (
        "Always Power On",
        "AC Power Recovery",
        "Manage → System → Autostart",
        "Stop action = **Shut down**",
        "Start earlier",
        "UPS",
        "Prod Audit",
        "arp -a",
        "selfheal",
        "open-vm-tools",
    ):
        assert needle in doc, needle
