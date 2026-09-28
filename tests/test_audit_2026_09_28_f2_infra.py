"""Audit 2026-09-28 F2 — infra/CI qapıları (AD-03/05/06/07, DB-02, FQ-TEST-1).

Statik yoxlamalar (nginx, deploy skripti, rol skriptləri, Dockerfile, lock-lar,
CI) + deploy funksiyasının saxta `docker` ilə davranış yoxlaması.
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
NGINX = ROOT / "docker/nginx/nginx.conf"
DEPLOY = ROOT / "scripts/deploy/remote_deploy.sh"
WORKFLOWS = ROOT / ".github/workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(conf: str, header: str) -> str:
    start = conf.index(header)
    depth = 0
    for index in range(conf.index("{", start), len(conf)):
        if conf[index] == "{":
            depth += 1
        elif conf[index] == "}":
            depth -= 1
            if depth == 0:
                return conf[start : index + 1]
    raise AssertionError(header)


def _function_body(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", _read(DEPLOY), flags=re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


# ── DB-02: nginx timeout-ları ──────────────────────────────────────────────

PROXY_HEADERS = (
    "proxy_set_header Host              $host;",
    "proxy_set_header X-Real-IP         $remote_addr;",
    "proxy_set_header X-EMS-Zone        $ems_zone;",
    "proxy_set_header X-Forwarded-For   $remote_addr;",
    "proxy_set_header X-Forwarded-Proto $scheme;",
)


def _long_locations(conf: str) -> list[str]:
    headers = ["location /ws/ {"] + [f"location ~ {rx} {{" for rx in re.findall(r"location ~ (\S+) \{", conf)]
    return [_block(conf, header) for header in headers]


def test_default_location_read_timeout_is_120s_and_long_paths_have_their_own():
    conf = _read(NGINX)
    root = _block(conf, "    location / {\n        # Kənar zonadan")
    assert "proxy_read_timeout    120s;" in root
    assert "proxy_read_timeout    900s;" not in root
    ws = _block(conf, "location /ws/ {")
    assert "proxy_read_timeout    900s;" in ws
    assert "proxy_set_header Upgrade $http_upgrade;" in ws
    regexes = re.findall(r"location ~ (\S+) \{", conf)
    assert len(regexes) == 2
    assert any("exams/import/" in rx for rx in regexes)
    assert any("api/ai-assistant/chat/" in rx for rx in regexes)


def test_long_locations_keep_proxy_headers_and_rate_limit_of_the_default_location():
    for block in _long_locations(_read(NGINX)):
        for header in PROXY_HEADERS:
            assert header in block, (header, block[:60])
        assert "limit_req zone=emsarena_general burst=1000 nodelay;" in block
        assert "proxy_pass $emsarena_app;" in block


@pytest.mark.parametrize(
    "path, long_timeout",
    [
        ("/exams/import/extract-jobs/", True),
        ("/api/ai-assistant/chat/", True),
        ("/exams/foo/results/export.xlsx", True),
        ("/audit/export.csv", True),
        # Zona qapısı yalnız `location /`-dadır — jurnal/manage regex-ə DÜŞMƏMƏLİDİR.
        ("/jurnal/abc/export.xlsx", False),
        ("/manage/exams/x/export.xlsx", False),
        ("/media/exams/import/a.pdf", False),
        ("/static/js/app.js", False),
        ("/exams/slug/", False),
    ],
)
def test_regex_locations_match_only_intended_paths(path, long_timeout):
    regexes = re.findall(r"location ~ (\S+) \{", _read(NGINX))
    assert any(re.search(rx, path) for rx in regexes) is long_timeout


def _nginx_version() -> tuple[int, ...]:
    if shutil.which("nginx") is None:
        return ()
    out = subprocess.run(["nginx", "-v"], capture_output=True, text=True).stderr
    match = re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(part) for part in match.groups()) if match else ()


# Prod image nginx:1.27 — `http2 on;` 1.25.1+ tələb edir; köhnə host nginx-i ötürülür.
@pytest.mark.skipif(_nginx_version() < (1, 25, 1), reason="nginx >= 1.25.1 yoxdur")
def test_nginx_config_parses(tmp_path):
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(tmp_path / "k.key")]
        + ["-out", str(tmp_path / "c.crt"), "-days", "1", "-subj", "/CN=x"],
        check=True,
        capture_output=True,
    )
    (tmp_path / "logs").mkdir()
    site = (
        _read(NGINX)
        .replace("/etc/nginx/certs/origin.crt", str(tmp_path / "c.crt"))
        .replace("/etc/nginx/certs/origin.key", str(tmp_path / "k.key"))
        .replace("/var/log/nginx/access.log", str(tmp_path / "logs/a.log"))
    )
    (tmp_path / "site.conf").write_text(site, encoding="utf-8")
    (tmp_path / "main.conf").write_text(
        f"pid {tmp_path}/n.pid;\nerror_log {tmp_path}/logs/e.log;\nevents {{}}\nhttp {{\n include {tmp_path}/site.conf;\n}}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["nginx", "-t", "-c", str(tmp_path / "main.conf"), "-p", str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ── DB-02: rol səviyyəli timeout-lar ──────────────────────────────────────


@pytest.mark.parametrize("script", ["docker/postgres-init/10-create-app-role.sh", "scripts/provision-app-db-role.sh"])
def test_role_scripts_set_role_level_timeouts(script):
    text = _read(ROOT / script)
    for setting, var in (
        ("statement_timeout", "statement_timeout"),
        ("lock_timeout", "lock_timeout"),
        ("idle_in_transaction_session_timeout", "idle_in_tx_timeout"),
    ):
        assert f"ALTER ROLE :\"app_role\" SET {setting} = :'{var}';" in text
    assert 'APP_DB_STATEMENT_TIMEOUT="${APP_DB_STATEMENT_TIMEOUT:-60s}"' in text
    assert 'APP_DB_LOCK_TIMEOUT="${APP_DB_LOCK_TIMEOUT:-10s}"' in text
    assert 'APP_DB_IDLE_IN_TRANSACTION_TIMEOUT="${APP_DB_IDLE_IN_TRANSACTION_TIMEOUT:-120s}"' in text


def _run_role_timeouts(tmp_path: Path, dotenv: str, **extra_env: str) -> tuple[subprocess.CompletedProcess, str]:
    if shutil.which("bash") is None:
        pytest.skip("bash yoxdur")
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    log = tmp_path / "docker.log"
    harness = (
        "set -euo pipefail\n"
        + _function_body("dotenv_value")
        + _function_body("apply_app_role_timeouts")
        + 'docker() { printf "%s\\n" "$*" >>"$DOCKER_LOG"; return "${FAKE_DOCKER_RC:-0}"; }\n'
        + f"APP_DIR={json.dumps(str(tmp_path))}\nDOCKER_LOG={json.dumps(str(log))}\nCOMPOSE_FILE=docker-compose.prod.yml\n"
        + "apply_app_role_timeouts\n"
    )
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path), **extra_env}
    result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, env=env, check=False)
    return result, (log.read_text(encoding="utf-8") if log.exists() else "")


def test_deploy_applies_role_timeouts_to_the_app_role(tmp_path):
    result, calls = _run_role_timeouts(
        tmp_path, "POSTGRES_USER=owner\nAPP_DATABASE_USER=emsarena_app\nAPP_DB_STATEMENT_TIMEOUT=45s\n"
    )
    assert result.returncode == 0, result.stderr
    assert "compose -f docker-compose.prod.yml exec -T postgres sh -c" in calls
    assert "ALTER ROLE \\\"emsarena_app\\\" SET statement_timeout = '45s'" in calls
    assert "SET lock_timeout = '10s'" in calls
    assert "SET idle_in_transaction_session_timeout = '120s'" in calls


@pytest.mark.parametrize(
    "dotenv",
    [
        "POSTGRES_USER=owner\n",  # ayrıca tətbiq rolu yoxdur
        "POSTGRES_USER=owner\nAPP_DATABASE_USER=owner\n",  # owner/superuser heç vaxt limitlənmir
        "POSTGRES_USER=owner\nAPP_DATABASE_USER=app\nAPP_DB_LOCK_TIMEOUT=10 seconds\n",  # yararsız dəyər
        'POSTGRES_USER=owner\nAPP_DATABASE_USER=app";DROP\n',  # identifikator deyil
    ],
)
def test_deploy_skips_role_timeouts_safely(tmp_path, dotenv):
    result, calls = _run_role_timeouts(tmp_path, dotenv)
    assert result.returncode == 0, result.stderr
    assert calls == ""


def test_role_timeout_failure_does_not_abort_the_deploy(tmp_path):
    result, calls = _run_role_timeouts(tmp_path, "POSTGRES_USER=owner\nAPP_DATABASE_USER=app\n", FAKE_DOCKER_RC="1")
    assert result.returncode == 0, result.stderr
    assert "exec -T postgres" in calls
    assert "role-level DB timeouts could not be applied" in result.stderr


def test_deploy_order_and_messages():
    body = _function_body("docker_deploy")
    assert body.index('export APT_SECURITY_REFRESH="${APT_SECURITY_REFRESH:-$(date +%G%V)}"') < body.index(
        'docker compose -f "$COMPOSE_FILE" build'
    ), "AD-05: apt layer həftəlik yenilənməlidir"
    assert (
        body.index("up -d postgres redis pgbouncer postgres-backup")
        < body.index("apply_app_role_timeouts")
        < body.index("/app/docker/release.sh")
    )
    rollback = _function_body("rollback_to_previous_image")
    assert "into a NEW database and swap names" in rollback
    assert "never pipe it into the live DB" in rollback


# ── AD-06: lock-lar ────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["production", "test"])
def test_lock_files_pin_every_package_with_hashes(name):
    text = _read(ROOT / f"requirements/{name}.lock")
    entries = re.split(r"\n(?=[A-Za-z0-9])", text.split("\n", 1)[1] if text.startswith("#") else text)
    pins = [entry for entry in entries if re.match(r"^[A-Za-z0-9]", entry)]
    assert len(pins) > 60
    for entry in pins:
        assert re.match(r"^[A-Za-z0-9_.\-]+==[^\s;]+", entry), entry[:80]
        assert "--hash=sha256:" in entry, entry[:80]


def test_lock_keeps_the_direct_pins_of_the_input_files():
    """Lock birbaşa `==` pin-ləri DƏYİŞMİR (yalnız keçid asılılıqlarını əlavə edir)."""
    lock = _read(ROOT / "requirements/production.lock").lower()
    direct = _read(ROOT / "requirements/base.txt") + "\n" + _read(ROOT / "requirements/production.txt")
    for line in direct.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s#]+)", line.strip())
        if not match:
            continue
        name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        pin = f"{name}=={match.group(3).lower()} "
        assert re.search(rf"^{re.escape(pin)}", lock, flags=re.MULTILINE), pin


def test_image_and_ci_install_from_the_hashed_locks():
    dockerfile = _read(ROOT / "docker/Dockerfile.prod")
    assert "pip install --no-cache-dir --require-hashes -r /app/requirements/production.lock" in dockerfile
    for workflow, lock in (
        ("_unit-tests.yml", "test"),
        ("_rls-txn-pool.yml", "test"),
        ("_build.yml", "test"),
        ("_e2e-smoke.yml", "test"),
        ("_js-tests.yml", "test"),
        ("_security.yml", "production"),
    ):
        assert f"pip install --require-hashes -r requirements/{lock}.lock" in _read(WORKFLOWS / workflow), workflow
    assert "scripts/deps/lock.sh --check" in _read(WORKFLOWS / "_lint.yml")
    assert os.access(ROOT / "scripts/deps/lock.sh", os.X_OK)


# ── AD-07 / FQ-TEST-1: CI qapıları ─────────────────────────────────────────


def _ci() -> dict:
    return yaml.safe_load(_read(WORKFLOWS / "ci.yml"))


def test_release_path_combines_shard_coverage_and_ci_success_requires_it():
    ci = _ci()
    jobs = ci["jobs"]
    shards = jobs["unit-tests-312"]["with"]
    assert "refs/heads/main" in shards["coverage-data"] and "refs/heads/Staging" in shards["coverage-data"]
    combine = jobs["coverage-combine"]
    assert combine["needs"] == "unit-tests-312"
    assert "refs/heads/main" in combine["if"] and "refs/heads/Staging" in combine["if"]
    script = "\n".join(step.get("run", "") for step in combine["steps"])
    assert "coverage combine coverage-data" in script
    assert "coverage report --fail-under=68" in script
    assert "coverage-combine" in jobs["ci-success"]["needs"]
    check = jobs["ci-success"]["steps"][0]["run"]
    assert 'COVERAGE_GATE_REQUIRED" == "1" && "${{ needs.coverage-combine.result }}" != "success"' in check
    # Deploy qapısı dəyişməyib (skip yayılması tələsi — always() + açıq nəticə).
    assert jobs["deploy-production"]["if"].startswith("always() && needs.ci-success.result == 'success'")


def test_unit_tests_upload_hidden_coverage_data_files():
    unit = yaml.safe_load(_read(WORKFLOWS / "_unit-tests.yml"))
    on = unit.get("on") or unit.get(True)
    assert on["workflow_call"]["inputs"]["coverage-data"]["default"] is False
    upload = next(
        step
        for step in unit["jobs"]["unit-tests"]["steps"]
        if step.get("name", "").endswith("shard coverage data") and "uses" in step
    )
    assert upload["with"]["include-hidden-files"] is True


def test_js_tests_job_runs_the_jsdom_harness_and_gates_ci():
    ci = _ci()
    assert ci["jobs"]["js-tests"]["uses"] == "./.github/workflows/_js-tests.yml"
    assert "js-tests" in ci["jobs"]["ci-success"]["needs"]
    workflow = _read(WORKFLOWS / "_js-tests.yml")
    assert "npm ci" in workflow and "npm test" in workflow
    assert 'EMS_REQUIRE_JSDOM: "1"' in workflow
    assert "tests/test_shipped_js_jsdom.py" in workflow
    package = json.loads(_read(ROOT / "tests/js/package.json"))
    assert package["scripts"]["test"] == "node --test"
    assert (ROOT / "tests/js/package-lock.json").exists()


# ── AD-03 leftover: sandbox skripti ────────────────────────────────────────


def test_sandbox_script_loads_env_agent_and_has_no_default_password():
    script = _read(ROOT / "scripts/claude_pg_sandbox.sh")
    assert '--env-file "$ROOT_DIR/.env.agent"' in script
    assert "emsarena_agent_password" not in script
