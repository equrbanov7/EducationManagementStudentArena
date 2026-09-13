"""
remote_deploy.sh — SHA teqi, deploy-öncəsi dump və avtomatik rollback
(2026-09-14 infra auditi, wave 2, P2-5) + `check --deploy` fail-level defoltu (P3-16).

Naxış tests/test_deploy_preflight.py-dəkidir: skriptdən yalnız lazımi
funksiyalar çıxarılır, xarici təsirli köməkçilər (DNS/TLS preflight, nginx
reload, HTTP gözləmə, replika healthcheck-i) stub-lanır, `docker` isə hər
çağırışı (və o andakı APP_IMAGE-i) log faylına yazan bash funksiyasıdır.
Beləliklə `docker_deploy`-un real axını konteyner qaldırmadan icra olunur.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/deploy/remote_deploy.sh"
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
REAL_FUNCTIONS = (
    "dotenv_value",
    "resolve_build_git_sha",
    "resolve_release_image",
    "capture_previous_app_image",
    "predeploy_database_backup",
    "wait_for_app_and_worker_health",
    "rollback_to_previous_image",
    "promote_release_image",
    "prune_old_release_images",
    "docker_deploy",
)
IMAGE_SERVICES = ("app", "celery_worker", "celery_worker_heavy", "celery_beat")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", _script(), flags=re.MULTILINE | re.DOTALL)
    assert match, f"{name}() remote_deploy.sh-də tapılmadı"
    return match.group(0)


# ── statik: compose `image:` və axın sırası ───────────────────────────────


def test_every_image_bearing_service_uses_the_app_image_variable():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    for service in IMAGE_SERVICES:
        assert compose["services"][service]["image"] == "${APP_IMAGE:-emsarena-prod:latest}", service


def test_deploy_flow_tags_backs_up_gates_and_promotes_in_order():
    body = _function_body("docker_deploy")
    order = [
        "resolve_build_git_sha",
        "resolve_release_image",
        "build\n",
        "capture_previous_app_image",
        "up -d postgres redis pgbouncer postgres-backup",
        "preflight_django_deploy_check",
        "predeploy_database_backup",
        "/app/docker/release.sh",
        "--remove-orphans",
        "wait_for_app_and_worker_health || {",
        "verify_running_build_sha",
        "promote_release_image",
        "prune_old_release_images",
    ]
    positions = [body.index(step) for step in order]
    assert positions == sorted(positions), "P2-5: docker_deploy addımlarının sırası pozulub"
    # Hər health/HTTP qapısının uğursuzluğu rollback-dan keçir.
    assert body.count("rollback_to_previous_image") == 3
    assert body.index("rollback_to_previous_image") < body.index("refresh_nginx_upstream")


def test_check_deploy_fail_level_defaults_to_warning_like_ci():
    script = _script()
    assert 'DEPLOY_CHECK_FAIL_LEVEL="${DEPLOY_CHECK_FAIL_LEVEL:-WARNING}"' in script, "P3-16"
    assert "dotenv_value DEPLOY_CHECK_FAIL_LEVEL" in script, "override .env-dən də oxunmalıdır"
    ci = (ROOT / ".github/workflows/_security.yml").read_text(encoding="utf-8")
    assert "check --deploy --fail-level WARNING" in ci


# ── davranış: saxta docker ilə docker_deploy icrası ──────────────────────

_HARNESS_STUBS = r"""
preflight_direct_dns() { :; }
validate_origin_cert() { :; }
remove_legacy_edge_firewall() { :; }
preflight_django_deploy_check() { echo "stub: preflight" ; }
refresh_nginx_upstream() { echo "stub: refresh_nginx_upstream"; }
reload_prometheus_config() { :; }
recreate_alertmanager() { :; }
verify_running_build_sha() { echo "stub: verify_running_build_sha"; }
wait_for_http() { return "${FAKE_HTTP_RC:-0}"; }
app_replicas_ready() {
  APP_HEALTH_SUMMARY="fake"
  [ "${FAKE_HEALTH:-ready}" = "ready" ]
}
worker_services_ready() {
  WORKER_HEALTH_SUMMARY="fake"
  [ "${FAKE_HEALTH:-ready}" = "ready" ]
}
docker() {
  printf '%s\t%s\n' "APP_IMAGE=${APP_IMAGE:-}" "$*" >>"$DOCKER_LOG"
  case "$*" in
    "compose -f "*" ps -q app")
      printf '%s\n' ${FAKE_APP_IDS:-}
      ;;
    "inspect --format {{.Config.Image}} "*)
      printf '%s' "${FAKE_PREV_IMAGE:-}"
      ;;
    "image inspect "*)
      return "${FAKE_PREV_EXISTS_RC:-0}"
      ;;
    *"exec -T postgres-backup /backup.sh")
      return "${FAKE_BACKUP_RC:-0}"
      ;;
    "image ls --format {{.Tag}} "*)
      printf '%b' "${FAKE_TAGS:-}"
      ;;
    *) ;;
  esac
  return 0
}
"""


def _run_deploy(tmp_path: Path, env: dict, function: str = "docker_deploy") -> tuple[subprocess.CompletedProcess, str]:
    if shutil.which("bash") is None:
        pytest.skip("bash yoxdur")
    (tmp_path / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET_KEY=x\n", encoding="utf-8")
    (tmp_path / "tmp").mkdir(exist_ok=True)
    log = tmp_path / "docker.log"
    if log.exists():
        log.unlink()
    harness = "set -euo pipefail\n"
    harness += "\n".join(_function_body(name) for name in REAL_FUNCTIONS)
    harness += _HARNESS_STUBS
    harness += (
        f"\nAPP_DIR={json.dumps(str(tmp_path))}\nDEPLOY_TMP={json.dumps(str(tmp_path / 'tmp'))}\n"
        f"DOCKER_LOG={json.dumps(str(log))}\n"
        "COMPOSE_FILE=docker-compose.prod.yml\nCOMPOSE_CONFIG=${DEPLOY_TMP}/compose-config.yml\n"
        "PING_JSON=${DEPLOY_TMP}/ping.json\nHEALTH_JSON=${DEPLOY_TMP}/health.json\n"
        "APP_BASE_URL=https://127.0.0.1\nPING_PATH=/ping/\nHEALTH_PATH=/health/\nEDGE_PROXY_MODE=lan\n"
        "DEPLOY_TIMEOUT_SECONDS=5\nAPP_REPLICAS=${APP_REPLICAS:-2}\nCELERY_REPLICAS=${CELERY_REPLICAS:-1}\n"
        "APP_IMAGE_REPOSITORY=emsarena-prod\n"
        "SKIP_PREDEPLOY_BACKUP=${SKIP_PREDEPLOY_BACKUP:-0}\n"
        "DEPLOY_ROLLBACK_ON_FAILURE=${DEPLOY_ROLLBACK_ON_FAILURE:-true}\n"
        "DEPLOY_KEEP_RELEASE_IMAGES=${DEPLOY_KEEP_RELEASE_IMAGES:-3}\n"
        "BUILD_GIT_SHA=${BUILD_GIT_SHA:-}\nAPP_IMAGE=${APP_IMAGE:-}\nPREVIOUS_APP_IMAGE=${PREVIOUS_APP_IMAGE:-}\n"
        f"{function}\n"
    )
    full_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)}
    full_env.update(env)
    result = subprocess.run(
        ["bash", "-c", harness], capture_output=True, text=True, env=full_env, cwd=str(tmp_path), check=False
    )
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    return result, calls


def _call_lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line.strip()]


_HAPPY_ENV = {
    "BUILD_GIT_SHA": "abc1234",
    "FAKE_APP_IDS": "c0ffee",
    "FAKE_PREV_IMAGE": "emsarena-prod:old1111",
    "FAKE_TAGS": "abc1234\\nold1111\\nkeep1\\nkeep2\\nkeep3\\ndrop4\\ndrop5\\nlatest\\n",
}


def test_happy_path_builds_sha_tag_dumps_before_release_and_promotes_latest(tmp_path):
    result, calls = _run_deploy(tmp_path, _HAPPY_ENV)
    assert result.returncode == 0, result.stderr
    lines = _call_lines(calls)

    build = next(line for line in lines if line.endswith("compose -f docker-compose.prod.yml build"))
    assert build.startswith("APP_IMAGE=emsarena-prod:abc1234\t"), "build SHA teqi ilə getməlidir"
    assert "Release image: emsarena-prod:abc1234" in result.stdout
    assert "Rollback target captured: emsarena-prod:old1111" in result.stdout

    backup = next(i for i, line in enumerate(lines) if line.endswith("exec -T postgres-backup /backup.sh"))
    release = next(i for i, line in enumerate(lines) if line.endswith("app /app/docker/release.sh"))
    assert backup < release, "dump miqrasiyadan ƏVVƏL alınmalıdır"
    assert any(line.endswith("up -d postgres redis pgbouncer postgres-backup") for line in lines)

    rollout = next(line for line in lines if "up -d --remove-orphans --scale app=2 --scale celery_worker=1" in line)
    assert rollout.startswith("APP_IMAGE=emsarena-prod:abc1234\t")

    promote = next(i for i, line in enumerate(lines) if line.endswith("tag emsarena-prod:abc1234 emsarena-prod:latest"))
    assert promote > release
    assert not any("up -d --no-build" in line for line in lines), "uğurlu deploy-da rollback olmamalıdır"

    # Köhnə teqlər: cari + rollback hədəfi + DEPLOY_KEEP_RELEASE_IMAGES=3 saxlanır, qalanı silinir.
    removed = [line.split("image rm ", 1)[1] for line in lines if "image rm " in line]
    assert removed == ["emsarena-prod:drop4", "emsarena-prod:drop5"]


def test_health_failure_rolls_back_to_the_previous_tag_and_fails_the_deploy(tmp_path):
    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "FAKE_HEALTH": "down"})
    assert result.returncode == 1
    lines = _call_lines(calls)

    rollback = [line for line in lines if "up -d --no-build" in line]
    assert len(rollback) == 1, calls
    assert rollback[0].startswith("APP_IMAGE=emsarena-prod:old1111\t"), "rollback əvvəlki teq ilə getməlidir"
    assert rollback[0].endswith(
        "--scale app=2 --scale celery_worker=1 app celery_worker celery_worker_heavy celery_beat"
    ), "yalnız image daşıyan servislər yenidən yaradılır"
    # Diaqnostika (ps/logs) rollback-dan əvvəl, `latest` heç vaxt dəyişmir.
    logs_index = next(i for i, line in enumerate(lines) if "logs --tail=200 app nginx celery_worker" in line)
    assert lines.index(rollback[0]) > logs_index
    assert not any(" tag " in line for line in lines), "uğursuz release latest-ə çevrilməməlidir"
    assert "ROLLING BACK TO emsarena-prod:old1111" in result.stderr
    assert "migrations from the failed release were NOT reverted" in result.stderr
    assert "stub: refresh_nginx_upstream" in result.stdout, "rollback-dan sonra nginx upstream təzələnməlidir"


def test_http_gate_failure_after_container_health_also_rolls_back(tmp_path):
    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "FAKE_HTTP_RC": "1"})
    assert result.returncode == 1
    rollback = [line for line in _call_lines(calls) if "up -d --no-build" in line]
    assert len(rollback) == 1 and rollback[0].startswith("APP_IMAGE=emsarena-prod:old1111\t")


def test_rollback_can_be_disabled_and_is_skipped_without_a_captured_target(tmp_path):
    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "FAKE_HEALTH": "down", "DEPLOY_ROLLBACK_ON_FAILURE": "false"})
    assert result.returncode == 1
    assert not any("up -d --no-build" in line for line in _call_lines(calls))
    assert "leaving the failed release in place" in result.stderr

    # İlk deploy / app konteyneri yoxdur → hədəf yoxdur, əl ilə əmr göstərilir.
    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "FAKE_HEALTH": "down", "FAKE_APP_IDS": ""})
    assert result.returncode == 1
    assert not any("up -d --no-build" in line for line in _call_lines(calls))
    assert "No rollback target was captured" in result.stderr
    assert "Manual rollback: APP_IMAGE=<previous tag>" in result.stderr


def test_previous_image_is_ignored_when_it_no_longer_exists_locally(tmp_path):
    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "FAKE_HEALTH": "down", "FAKE_PREV_EXISTS_RC": "1"})
    assert result.returncode == 1
    assert "no longer exists locally" in result.stderr
    assert not any("up -d --no-build" in line for line in _call_lines(calls))


def test_predeploy_backup_skip_flag_and_fail_closed_on_dump_error(tmp_path):
    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "SKIP_PREDEPLOY_BACKUP": "1"})
    assert result.returncode == 0, result.stderr
    assert not any("/backup.sh" in line for line in _call_lines(calls))
    assert "pre-deploy database dump skipped" in result.stderr

    result, calls = _run_deploy(tmp_path, {**_HAPPY_ENV, "FAKE_BACKUP_RC": "1"})
    assert result.returncode == 1
    assert "Pre-deploy database dump FAILED" in result.stderr
    lines = _call_lines(calls)
    assert not any(line.endswith("app /app/docker/release.sh") for line in lines), "dump-sız miqrasiya olmamalıdır"
    assert not any("--remove-orphans" in line for line in lines)


def test_release_image_falls_back_to_a_timestamped_manual_tag(tmp_path):
    result, _ = _run_deploy(tmp_path, {"BUILD_GIT_SHA": "unknown"}, function="resolve_release_image")
    assert result.returncode == 0, result.stderr
    assert re.search(r"^Release image: emsarena-prod:manual-\d{8}T\d{6}Z$", result.stdout.strip(), flags=re.M)
