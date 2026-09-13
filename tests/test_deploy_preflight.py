"""
remote_deploy.sh fail-closed qapıları (Codex audit 2026-09-13: P1-08, P1-07, §22).

Statik yoxlamalar skripti oxuyur; davranış yoxlamaları isə skriptdən yalnız
lazımi funksiyaları çıxarıb saxta `docker` shim-i ilə bash-da icra edir
(bash 3.2-də də işləyir — `mapfile` tələb edən worker funksiyası burada
icra olunmur, yalnız statik yoxlanır).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/deploy/remote_deploy.sh"
FUNCTIONS = ("dotenv_value", "resolve_build_git_sha", "preflight_django_deploy_check", "verify_running_build_sha")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", _script(), flags=re.MULTILINE | re.DOTALL)
    assert match, f"{name}() remote_deploy.sh-də tapılmadı"
    return match.group(0)


# ── statik: axın sırası və qapılar ────────────────────────────────────────


def test_deploy_runs_django_check_deploy_inside_image_before_release_and_restart():
    body = _function_body("docker_deploy")
    assert "preflight_django_deploy_check" in body
    assert body.index("preflight_django_deploy_check") > body.index("build\n")
    assert body.index("preflight_django_deploy_check") < body.index("/app/docker/release.sh")
    assert body.index("preflight_django_deploy_check") < body.index("--remove-orphans")

    preflight = _function_body("preflight_django_deploy_check")
    assert "python manage.py check --deploy --fail-level" in preflight
    assert "run --rm -T -e RUN_RELEASE_ON_START=false app" in preflight
    assert "exit 1" in preflight
    assert 'DEPLOY_CHECK_FAIL_LEVEL="${DEPLOY_CHECK_FAIL_LEVEL:-ERROR}"' in _script()


def test_deploy_refuses_insecure_transport_flag_in_production_env():
    preflight = _function_body("preflight_django_deploy_check")
    assert "dotenv_value INSECURE_TRANSPORT_OK" in preflight
    assert "1|true|yes|on)" in preflight


def test_health_wait_includes_celery_services_and_dumps_their_logs():
    body = _function_body("docker_deploy")
    assert "app_replicas_ready && worker_services_ready" in body
    assert "logs --tail=200 app nginx celery_worker celery_worker_heavy celery_beat" in body

    workers = _function_body("worker_services_ready")
    for service in ("celery_worker:${CELERY_REPLICAS}", "celery_worker_heavy:1", "celery_beat:1"):
        assert service in workers


def test_deploy_verifies_running_build_sha_after_health_gate():
    body = _function_body("docker_deploy")
    assert "resolve_build_git_sha" in body
    assert body.index("resolve_build_git_sha") < body.index("build\n")
    assert "verify_running_build_sha" in body
    assert body.index("verify_running_build_sha") > body.index('"200 207" "$HEALTH_JSON"')

    resolve = _function_body("resolve_build_git_sha")
    assert "GITHUB_SHA" in resolve
    assert "export BUILD_GIT_SHA" in resolve
    # Valideyn qovluqdakı yad repo-nun HEAD-i götürülməsin.
    assert '[ -d "${APP_DIR}/.git" ]' in resolve


def test_rsync_excludes_keep_runtime_state_but_not_deploy_scripts():
    excludes = (ROOT / "scripts/deploy/rsync-excludes.txt").read_text(encoding="utf-8").split()
    assert ".env" in excludes
    assert "docker/nginx/certs/" in excludes
    assert not any(item.startswith("scripts") or item.startswith("docker/build") for item in excludes)


# ── davranış: saxta docker ilə bash icrası ────────────────────────────────

_FAKE_DOCKER = r"""
docker() {
  case "$*" in
    *"check --deploy"*)
      printf '%s' "$FAKE_CHECK_OUTPUT"
      return "${FAKE_CHECK_RC:-0}"
      ;;
    *) echo "docker $*" >&2 ;;
  esac
}
"""


def _run_bash(function: str, env: dict, app_dir: Path, health_json: Path | None = None) -> subprocess.CompletedProcess:
    if shutil.which("bash") is None:
        pytest.skip("bash yoxdur")
    harness = "set -uo pipefail\n"
    harness += "\n".join(_function_body(name) for name in FUNCTIONS)
    harness += _FAKE_DOCKER
    harness += f"\nAPP_DIR={json.dumps(str(app_dir))}\nDEPLOY_TMP={json.dumps(str(app_dir / 'tmp'))}\n"
    harness += "COMPOSE_FILE=docker-compose.prod.yml\nDEPLOY_CHECK_FAIL_LEVEL=${DEPLOY_CHECK_FAIL_LEVEL:-ERROR}\n"
    harness += f"HEALTH_JSON={json.dumps(str(health_json or app_dir / 'health.json'))}\n"
    harness += f"BUILD_GIT_SHA=${{BUILD_GIT_SHA:-}}\n{function}\n"
    (app_dir / "tmp").mkdir(exist_ok=True)
    full_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(app_dir)}
    full_env.update(env)
    return subprocess.run(
        ["bash", "-c", harness], capture_output=True, text=True, env=full_env, cwd=str(app_dir), check=False
    )


def test_preflight_fails_closed_on_django_check_errors(tmp_path):
    result = _run_bash(
        "preflight_django_deploy_check",
        {"FAKE_CHECK_OUTPUT": "ERRORS:\n?: (security.E001) bad\n", "FAKE_CHECK_RC": "1"},
        tmp_path,
    )
    assert result.returncode == 1
    assert "Django deployment preflight FAILED" in result.stderr
    assert "(security.E001)" in result.stderr


def test_preflight_reports_security_warnings_loudly_but_continues(tmp_path):
    output = "WARNINGS:\n?: (security.W004) HSTS\n?: (security.W008) SSL redirect\n?: (security.W012) session cookie\n"
    result = _run_bash("preflight_django_deploy_check", {"FAKE_CHECK_OUTPUT": output, "FAKE_CHECK_RC": "0"}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "DJANGO DEPLOY CHECK WARNINGS" in result.stderr
    for code in ("W004", "W008", "W012"):
        assert f"(security.{code})" in result.stderr
    assert "DEPLOY_CHECK_FAIL_LEVEL=WARNING" in result.stderr


def test_preflight_passes_quietly_without_warnings(tmp_path):
    result = _run_bash(
        "preflight_django_deploy_check",
        {"FAKE_CHECK_OUTPUT": "System check identified no issues (0 silenced).\n", "FAKE_CHECK_RC": "0"},
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "passed with no warnings" in result.stdout
    assert "WARNINGS" not in result.stderr


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", '"on"'])
def test_preflight_refuses_insecure_transport_ok_in_env_file(tmp_path, value):
    (tmp_path / ".env").write_text(f"SECRET_KEY=x\nINSECURE_TRANSPORT_OK={value}\n", encoding="utf-8")
    result = _run_bash(
        "preflight_django_deploy_check",
        {"FAKE_CHECK_OUTPUT": "System check identified no issues (0 silenced).\n", "FAKE_CHECK_RC": "0"},
        tmp_path,
    )
    assert result.returncode == 1
    assert "INSECURE_TRANSPORT_OK" in result.stderr
    # docker heç çağırılmamalıdır — bayraq check-dən ƏVVƏL kəsir.
    assert "check --deploy" not in result.stderr


def test_preflight_allows_false_insecure_transport_flag(tmp_path):
    (tmp_path / ".env").write_text("INSECURE_TRANSPORT_OK=False\n", encoding="utf-8")
    result = _run_bash(
        "preflight_django_deploy_check",
        {"FAKE_CHECK_OUTPUT": "System check identified no issues (0 silenced).\n", "FAKE_CHECK_RC": "0"},
        tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_build_sha_resolution_prefers_explicit_then_github_sha_then_unknown(tmp_path):
    sha = "0123456789abcdef0123456789abcdef01234567"
    explicit = _run_bash("resolve_build_git_sha", {"BUILD_GIT_SHA": "abcdef1", "GITHUB_SHA": sha}, tmp_path)
    assert explicit.stdout.strip() == "Build source commit: abcdef1"

    github = _run_bash("resolve_build_git_sha", {"GITHUB_SHA": sha}, tmp_path)
    assert github.stdout.strip() == f"Build source commit: {sha}"

    nothing = _run_bash("resolve_build_git_sha", {}, tmp_path)
    assert nothing.stdout.strip() == "Build source commit: unknown"

    garbage = _run_bash("resolve_build_git_sha", {"GITHUB_SHA": "not a sha; rm -rf /"}, tmp_path)
    assert garbage.stdout.strip() == "Build source commit: unknown"


@pytest.mark.parametrize(
    ("payload", "expected_rc", "needle"),
    [
        ({"status": "healthy", "build": {"sha": "abc1234"}}, 0, "Running image verified: build.sha=abc1234"),
        ({"status": "healthy", "build": {"sha": "old9999"}}, 1, "Image drift detected"),
        ({"status": "healthy"}, 1, "build.sha=missing"),
    ],
)
def test_running_build_sha_is_compared_with_the_built_commit(tmp_path, payload, expected_rc, needle):
    health = tmp_path / "health.json"
    health.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_bash("verify_running_build_sha", {"BUILD_GIT_SHA": "abc1234"}, tmp_path, health)
    assert result.returncode == expected_rc, result.stderr
    assert needle in (result.stdout + result.stderr)


def test_running_build_sha_check_is_skipped_when_source_commit_is_unknown(tmp_path):
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"status": "healthy", "build": {"sha": "whatever"}}), encoding="utf-8")
    result = _run_bash("verify_running_build_sha", {"BUILD_GIT_SHA": "unknown"}, tmp_path, health)
    assert result.returncode == 0
    assert "skipping image drift verification" in result.stderr
