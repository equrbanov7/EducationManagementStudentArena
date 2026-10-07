"""Təhlükəsizlik auditi 2026-10-07 — exporter-lər least privilege ilə, promtail docker.sock-suz.

DB-siz qapılar:
  * compose / promtail YAML — xam docker.sock yalnız proxy-də (və privileged cadvisor-da),
    proxy yalnız GET, exporter-lər monitor dəyişənlərinə köhnə girişi fallback kimi saxlayır;
  * compose interpolyasiyası (mini interpolator) — dəyişən yoxdursa effektiv dəyərlər
    bu günkü ilə eynidir, varsa exporter mühitində owner/əsas parol QALMIR;
  * pgbouncer / redis start sarğıları real `sh` ilə (image entrypoint-i stub);
  * provision_monitor_role.sh və remote_deploy.sh funksiyaları saxta `docker` ilə;
  * prod-secrets-generate.yml — sirr dəyəri heç vaxt çap olunmur, real bash ilə icra.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.prod.yml"
PROMTAIL = ROOT / "docker/promtail/promtail-config.yml"
PGBOUNCER_WRAPPER = ROOT / "docker/pgbouncer/entrypoint.sh"
REDIS_DIR = ROOT / "docker/redis"
RENDER = ROOT / "docker/render-template.sh"
PROVISION = ROOT / "scripts/deploy/provision_monitor_role.sh"
DEPLOY = ROOT / "scripts/deploy/remote_deploy.sh"
PROD_AUDIT = ROOT / "scripts/ops/prod_audit.sh"
WORKFLOW = ROOT / ".github/workflows/prod-secrets-generate.yml"

DB_PW = "Zx9-TestMonitorPw_0123456789abcdefABCDEF"
REDIS_PW = "Rd7-TestMonitorPw_0123456789abcdefABCDEF"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _services() -> dict:
    return yaml.safe_load(_read(COMPOSE))["services"]


def _base_env(tmp_path: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path), "LC_ALL": "C"}


def _need(tool: str) -> None:
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} yoxdur")


# ── Mini compose interpolator (${V}, ${V:-x}, ${V-x}, ${V:+x}, ${V+x}, ${V:?e}; iç-içə) ──


def _interpolate(value: str, env: dict[str, str]) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        if value.startswith("$$", index):
            out.append("$")
            index += 2
            continue
        if value.startswith("${", index):
            depth, cursor = 0, index
            while cursor < len(value):
                if value.startswith("${", cursor):
                    depth += 1
                    cursor += 2
                    continue
                if value[cursor] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                cursor += 1
            out.append(_resolve(value[index + 2 : cursor], env))
            index = cursor + 1
            continue
        out.append(value[index])
        index += 1
    return "".join(out)


def _resolve(expr: str, env: dict[str, str]) -> str:
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(:-|:\+|:\?|-|\+|\?)?(.*)$", expr, flags=re.DOTALL)
    assert match, expr
    name, op, arg = match.groups()
    value = env.get(name)
    if op is None:
        return value or ""
    if op == ":-":
        return value if value else _interpolate(arg, env)
    if op == "-":
        return value if value is not None else _interpolate(arg, env)
    if op == ":+":
        return _interpolate(arg, env) if value else ""
    if op == "+":
        return _interpolate(arg, env) if value is not None else ""
    assert value, f"{name}: {arg}"
    return value


def test_mini_interpolator_matches_compose_semantics():
    env = {"A": "a", "E": ""}
    assert _interpolate("${A:-x}|${E:-x}|${N:-x}|${E-x}|${N-x}", env) == "a|x|x||x"
    assert _interpolate("${A:+y}|${E:+y}|${E+y}|${N+y}|${N:-${A:-z}}", env) == "y||y||a"


# ── Promtail ↔ docker-socket-proxy ──────────────────────────────────────────

_PROXY_ALLOWED = {"CONTAINERS", "NETWORKS", "PING", "VERSION"}
_PROXY_API_FLAGS = {
    "AUTH", "SECRETS", "POST", "BUILD", "COMMIT", "CONFIGS", "CONTAINERS", "DISTRIBUTION", "EVENTS", "EXEC",
    "GRPC", "IMAGES", "INFO", "NETWORKS", "NODES", "PING", "PLUGINS", "SERVICES", "SESSION", "SWARM",
    "SYSTEM", "TASKS", "VERSION", "VOLUMES", "ALLOW_START", "ALLOW_STOP", "ALLOW_RESTARTS",
}  # fmt: skip


def test_promtail_has_no_docker_socket_and_reaches_docker_through_the_proxy():
    promtail = _services()["promtail"]
    assert not [v for v in promtail["volumes"] if "docker.sock" in v or v.startswith("/var/run")]
    assert set(promtail["networks"]) == {"emsarena-network", "docker-api"}
    assert "docker-socket-proxy" in promtail["depends_on"]
    sd = yaml.safe_load(_read(PROMTAIL))["scrape_configs"][0]["docker_sd_configs"]
    assert [entry["host"] for entry in sd] == ["tcp://docker-socket-proxy:2375"]
    assert "docker.sock" not in "".join(
        line for line in _read(PROMTAIL).splitlines() if not line.lstrip().startswith("#")
    )


def test_docker_socket_proxy_is_get_only_with_the_minimum_api_sections():
    proxy = _services()["docker-socket-proxy"]
    env = {key: str(value) for key, value in proxy["environment"].items()}
    assert env["POST"] == "0"
    for flag in _PROXY_API_FLAGS:
        # İmage defoltlarına güvənilmir (EVENTS defoltu 1-dir) — hər bayraq açıq yazılıb.
        assert flag in env, flag
        assert env[flag] == ("1" if flag in _PROXY_ALLOWED else "0"), flag
    assert proxy["volumes"] == ["/var/run/docker.sock:/var/run/docker.sock:ro"]
    assert "ports" not in proxy and "expose" not in proxy
    assert proxy["networks"] == ["docker-api"]
    assert re.fullmatch(r"tecnativa/docker-socket-proxy:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", proxy["image"])
    assert "no-new-privileges:true" in proxy["security_opt"]
    assert proxy["cap_drop"] == ["ALL"] and proxy["read_only"] is True
    assert set(proxy["tmpfs"]) == {"/run", "/tmp"}
    assert not proxy.get("privileged")
    limits = proxy["deploy"]["resources"]["limits"]
    assert re.fullmatch(r"\$\{DOCKER_PROXY_CPU_LIMIT:-[0-9.]+\}", limits["cpus"])
    assert re.fullmatch(r"\$\{DOCKER_PROXY_MEM_LIMIT:-\d+M\}", limits["memory"])


def test_docker_api_network_is_internal_and_holds_only_proxy_and_promtail():
    compose = yaml.safe_load(_read(COMPOSE))
    assert compose["networks"]["docker-api"]["internal"] is True
    members = {name for name, svc in compose["services"].items() if "docker-api" in (svc.get("networks") or [])}
    assert members == {"docker-socket-proxy", "promtail"}


def test_only_the_proxy_and_the_privileged_cadvisor_mount_the_docker_socket():
    for name, svc in _services().items():
        for volume in svc.get("volumes", []):
            source = str(volume).split(":")[0]
            if "docker.sock" in source or source in {"/var/run", "/run"}:
                assert name in {"docker-socket-proxy", "cadvisor"}, f"{name}: {volume}"
                assert str(volume).endswith(":ro"), f"{name}: {volume}"
    # cadvisor istisnasının səbəbi compose-da sənədləşib.
    cadvisor_block = _read(COMPOSE).split("\n  cadvisor:\n", 1)[1].split("\n  redis_exporter:\n", 1)[0]
    assert "socket-proxy heç bir sərhəd yaratmır" in cadvisor_block


# ── Exporter-lər: monitor dəyişənləri, köhnə giriş fallback kimi ────────────────


def test_exporters_reference_monitor_vars_with_the_old_credentials_as_fallback():
    services = _services()
    pgx = services["postgres_exporter"]["environment"]
    assert pgx["DATA_SOURCE_USER"] == "${MONITOR_DB_USER:-${POSTGRES_USER}}"
    assert pgx["DATA_SOURCE_PASS"] == "${MONITOR_DB_PASSWORD:-${POSTGRES_PASSWORD}}"
    assert pgx["DATA_SOURCE_URI"] == "postgres:5432/${POSTGRES_DB}?sslmode=disable"
    pgbx = services["pgbouncer_exporter"]["environment"]["PGBOUNCER_EXPORTER_CONNECTION_STRING"]
    assert pgbx == (
        "postgres://${MONITOR_DB_USER:-${POSTGRES_USER}}:${MONITOR_DB_PASSWORD:-${POSTGRES_PASSWORD}}"
        "@pgbouncer:5432/pgbouncer?sslmode=disable"
    )
    rdx = services["redis_exporter"]["environment"]
    assert rdx["REDIS_USER"] == "${REDIS_MONITOR_PASSWORD:+monitor}"
    assert rdx["REDIS_PASSWORD"] == "${REDIS_MONITOR_PASSWORD:-${REDIS_PASSWORD}}"
    pgb = services["pgbouncer"]
    assert pgb["environment"]["MONITOR_DB_USER"] == "${MONITOR_DB_USER:-}"
    assert pgb["environment"]["MONITOR_DB_PASSWORD"] == "${MONITOR_DB_PASSWORD:-}"
    assert pgb["entrypoint"] == ["/bin/sh", "/opt/ems/pgbouncer-entrypoint.sh"]
    # Entrypoint dəyişəndə image CMD-i sıfırlanır — image defoltu ilə eyni əmr açıq yazılmalıdır.
    assert pgb["command"] == ["/usr/bin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
    assert "./docker/pgbouncer/entrypoint.sh:/opt/ems/pgbouncer-entrypoint.sh:ro" in pgb["volumes"]
    assert services["redis"]["environment"]["REDIS_MONITOR_PASSWORD"] == "${REDIS_MONITOR_PASSWORD:-}"


def _exporter_env(env: dict[str, str]) -> dict[str, dict[str, str]]:
    services = _services()
    return {
        name: {key: _interpolate(str(value), env) for key, value in services[name]["environment"].items()}
        for name in ("postgres_exporter", "pgbouncer_exporter", "redis_exporter", "pgbouncer", "redis")
    }


_BASE = {"POSTGRES_USER": "owner", "POSTGRES_PASSWORD": "OWNER-PW", "POSTGRES_DB": "db", "REDIS_PASSWORD": "MAIN-PW"}


@pytest.mark.parametrize(
    "extra",
    [
        {},
        # remote_deploy.sh fallback-i: shell-də BOŞ ixrac (.env-dəki dəyərdən üstündür).
        {"MONITOR_DB_USER": "", "MONITOR_DB_PASSWORD": "", "REDIS_MONITOR_PASSWORD": ""},
    ],
    ids=["absent", "exported-empty"],
)
def test_absent_monitor_vars_keep_todays_effective_credentials(extra):
    env = _exporter_env({**_BASE, **extra})
    assert env["postgres_exporter"]["DATA_SOURCE_USER"] == "owner"
    assert env["postgres_exporter"]["DATA_SOURCE_PASS"] == "OWNER-PW"
    assert (
        env["pgbouncer_exporter"]["PGBOUNCER_EXPORTER_CONNECTION_STRING"]
        == "postgres://owner:OWNER-PW@pgbouncer:5432/pgbouncer?sslmode=disable"
    )
    assert env["redis_exporter"]["REDIS_USER"] == ""  # default istifadəçi, bu günkü kimi
    assert env["redis_exporter"]["REDIS_PASSWORD"] == "MAIN-PW"
    assert env["pgbouncer"]["MONITOR_DB_PASSWORD"] == "" and env["redis"]["REDIS_MONITOR_PASSWORD"] == ""


def test_monitor_vars_switch_exporters_and_drop_the_owner_and_main_passwords():
    env = _exporter_env(
        {
            **_BASE,
            "MONITOR_DB_USER": "emsarena_monitor",
            "MONITOR_DB_PASSWORD": DB_PW,
            "REDIS_MONITOR_PASSWORD": REDIS_PW,
        }
    )
    assert env["postgres_exporter"]["DATA_SOURCE_USER"] == "emsarena_monitor"
    assert env["postgres_exporter"]["DATA_SOURCE_PASS"] == DB_PW
    assert env["pgbouncer_exporter"]["PGBOUNCER_EXPORTER_CONNECTION_STRING"].startswith(
        f"postgres://emsarena_monitor:{DB_PW}@"
    )
    assert env["redis_exporter"] == {
        "REDIS_ADDR": "redis://redis:6379",
        "REDIS_USER": "monitor",
        "REDIS_PASSWORD": REDIS_PW,
    }
    for name in ("postgres_exporter", "pgbouncer_exporter", "redis_exporter"):
        flat = json.dumps(env[name])
        assert "OWNER-PW" not in flat and "MAIN-PW" not in flat, name


# ── docker/pgbouncer/entrypoint.sh (real sh, image entrypoint stub) ─────────────


def _run_pgbouncer_wrapper(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess, Path]:
    _need("sh")
    fake = tmp_path / "image-entrypoint.sh"
    fake.write_text(
        "#!/bin/sh\nprintf 'ARGS:%s\\n' \"$*\"\nprintf 'STATS:%s\\n' \"${STATS_USERS-<unset>}\"\n"
        "printf 'PW:%s\\n' \"${MONITOR_DB_PASSWORD:-<unset>}\"\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    auth = tmp_path / "userlist.txt"
    result = subprocess.run(
        ["sh", str(PGBOUNCER_WRAPPER), "/usr/bin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"],
        capture_output=True,
        text=True,
        check=False,
        env={**_base_env(tmp_path), "PGBOUNCER_IMAGE_ENTRYPOINT": str(fake), "AUTH_FILE": str(auth), **env},
    )
    return result, auth


def test_pgbouncer_wrapper_without_monitor_vars_is_a_pure_passthrough(tmp_path):
    result, auth = _run_pgbouncer_wrapper(tmp_path, ADMIN_USERS="owner")
    assert result.returncode == 0, result.stderr
    assert "ARGS:/usr/bin/pgbouncer /etc/pgbouncer/pgbouncer.ini" in result.stdout
    assert "STATS:<unset>" in result.stdout
    assert not auth.exists()


def test_pgbouncer_wrapper_adds_a_stats_only_user_without_leaking_the_password(tmp_path):
    env = {"ADMIN_USERS": "owner", "MONITOR_DB_USER": "emsarena_monitor", "MONITOR_DB_PASSWORD": DB_PW}
    result, auth = _run_pgbouncer_wrapper(tmp_path, **env)
    assert result.returncode == 0, result.stderr
    assert "STATS:emsarena_monitor" in result.stdout
    assert "PW:<unset>" in result.stdout, "parol pgbouncer prosesinin mühitindən silinməlidir"
    assert DB_PW not in result.stdout + result.stderr
    assert auth.read_text(encoding="utf-8") == f'"emsarena_monitor" "{DB_PW}"\n'
    assert stat.S_IMODE(auth.stat().st_mode) == 0o600
    # Konteyner restartında (fayl qalır) sətir təkrarlanmır; mövcud STATS_USERS saxlanılır.
    result, auth = _run_pgbouncer_wrapper(tmp_path, STATS_USERS="ops", **env)
    assert "STATS:ops,emsarena_monitor" in result.stdout
    assert auth.read_text(encoding="utf-8").count("emsarena_monitor") == 1


@pytest.mark.parametrize(
    "user,password",
    [
        ("emsarena_monitor", 'bad"pass word-0123456789'),
        ("emsarena_monitor", "x1y2z3"),
        ("owner", DB_PW),  # owner adı → image owner sətrini yazmazdı
        ("Monitor", DB_PW),
        ("emsarena_monitor", ""),
        ("", DB_PW),
    ],
)
def test_pgbouncer_wrapper_skips_unsafe_values_and_keeps_the_old_behaviour(tmp_path, user, password):
    result, auth = _run_pgbouncer_wrapper(
        tmp_path, ADMIN_USERS="owner", MONITOR_DB_USER=user, MONITOR_DB_PASSWORD=password
    )
    assert result.returncode == 0, result.stderr
    assert "ARGS:/usr/bin/pgbouncer /etc/pgbouncer/pgbouncer.ini" in result.stdout
    assert "STATS:<unset>" in result.stdout
    assert not auth.exists() or user not in auth.read_text(encoding="utf-8")
    if password:
        assert password not in result.stdout + result.stderr


# ── docker/redis/entrypoint.sh: monitor ACL istifadəçisi ───────────────────────

_EXPECTED_ACL = (
    "on resetkeys resetchannels -@all +ping +info +client|setname +slowlog|get +slowlog|len "
    "+latency|latest +latency|histogram"
)


def _run_redis_entrypoint(tmp_path: Path, monitor_password: str | None, check_rc: int = 0):
    _need("sh")
    conf_dir = tmp_path / "etc-redis"
    conf_dir.mkdir()
    shutil.copy(REDIS_DIR / "redis.conf.tmpl", conf_dir / "redis.conf.tmpl")
    shutil.copy(RENDER, conf_dir / "render-template.sh")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker-entrypoint.sh").write_text(
        "#!/bin/sh\nprintf 'ARGS:%s\\n' \"$*\"\nprintf 'MONPW:%s\\n' \"${REDIS_MONITOR_PASSWORD:-<unset>}\"\n",
        encoding="utf-8",
    )
    # `timeout 2 <redis-server> <conf>` → stub: yoxlama konfiqini saxlayır, kodu qaytarır.
    (fake_bin / "timeout").write_text('#!/bin/sh\nshift\nexec "$@"\n', encoding="utf-8")
    calls = tmp_path / "check-calls"
    fake_server = tmp_path / "fake-redis-server"
    fake_server.write_text(
        f'#!/bin/sh\ncat "$1" >> "{calls}"\nexit {check_rc}\n',
        encoding="utf-8",
    )
    for path in (fake_bin / "docker-entrypoint.sh", fake_bin / "timeout", fake_server):
        path.chmod(0o755)
    rendered = tmp_path / "redis.conf"
    env = {
        **_base_env(tmp_path),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "REDIS_PASSWORD": "MAIN-PW",
        "REDIS_MAXMEMORY": "512mb",
        "REDIS_CONF_DIR": str(conf_dir),
        "REDIS_RENDERED_CONF": str(rendered),
        "REDIS_SERVER_BIN": str(fake_server),
    }
    if monitor_password is not None:
        env["REDIS_MONITOR_PASSWORD"] = monitor_password
    result = subprocess.run(["sh", str(REDIS_DIR / "entrypoint.sh")], capture_output=True, text=True, env=env)
    return result, rendered.read_text(encoding="utf-8"), (calls.read_text(encoding="utf-8") if calls.exists() else "")


def test_redis_monitor_acl_is_read_only_and_validated_before_it_reaches_the_config(tmp_path):
    result, conf, checked = _run_redis_entrypoint(tmp_path, REDIS_PW)
    assert result.returncode == 0, result.stderr
    line = f'user monitor {_EXPECTED_ACL} ">{REDIS_PW}"'
    assert line in conf.splitlines()
    assert line in checked.splitlines() and "port 0" in checked and "unixsocket " in checked
    assert REDIS_PW not in result.stdout + result.stderr
    assert "MONPW:<unset>" in result.stdout, "sirr redis-server mühitindən silinməlidir"
    rules = _EXPECTED_ACL.split()
    assert rules.index("-@all") < min(i for i, rule in enumerate(rules) if rule.startswith("+"))
    # requirepass-ı qaytaran CONFIG, açarlar, kanallar, CLIENT LIST — heç biri.
    assert not [r for r in rules if r.startswith(("+config", "+@", "~", "&", "%")) or r in {"allkeys", "allcommands"}]
    assert 'requirepass "MAIN-PW"' in conf


@pytest.mark.parametrize("password", [None, ""])
def test_redis_without_monitor_password_renders_todays_config(tmp_path, password):
    result, conf, checked = _run_redis_entrypoint(tmp_path, password)
    assert result.returncode == 0, result.stderr
    assert "user " not in conf and checked == ""


@pytest.mark.parametrize(
    "password,check_rc",
    [
        (REDIS_PW, 1),  # redis-server qaydanı rədd etdi → FATAL əvəzinə ACL-siz start
        (REDIS_PW, 127),  # yoxlayıcı yoxdur
        ('bad"pass word 0123456789', 0),
        ("x1y2z3", 0),
    ],
)
def test_redis_skips_the_acl_user_when_anything_is_off_and_still_starts(tmp_path, password, check_rc):
    result, conf, _ = _run_redis_entrypoint(tmp_path, password, check_rc=check_rc)
    assert result.returncode == 0, result.stderr
    assert "ARGS:redis-server" in result.stdout
    assert "user monitor" not in conf
    assert "monitor ACL user NOT enabled" in result.stderr
    assert password not in result.stdout + result.stderr


# ── scripts/deploy/provision_monitor_role.sh (saxta docker) ───────────────────


def _run_provision(tmp_path: Path, dotenv: str, docker_rc: int = 0, docker_out: str = "", **env: str):
    _need("bash")
    app = tmp_path / "app"
    app.mkdir(exist_ok=True)
    (app / ".env").write_text(dotenv, encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    argv_log, stdin_log = tmp_path / "docker-argv", tmp_path / "docker-stdin"
    (fake_bin / "docker").write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{argv_log}'\n"
        f"cat >> '{stdin_log}'\n"
        f"printf '%s\\n' {json.dumps(docker_out)}\n"
        f"exit {docker_rc}\n",
        encoding="utf-8",
    )
    (fake_bin / "docker").chmod(0o755)
    result = subprocess.run(
        ["bash", str(PROVISION)],
        capture_output=True,
        text=True,
        env={
            **_base_env(tmp_path),
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "APP_DIR": str(app),
            **env,
        },
    )
    read = lambda p: p.read_text(encoding="utf-8") if p.exists() else ""  # noqa: E731
    return result, read(argv_log), read(stdin_log)


_DOTENV = f"POSTGRES_USER=owner\nAPP_DATABASE_USER=emsarena_app\nMONITOR_DB_PASSWORD={DB_PW}\n"


def test_provision_passes_the_password_only_on_stdin_and_hardens_the_role(tmp_path):
    result, argv, stdin = _run_provision(
        tmp_path, _DOTENV, docker_out="monitor role emsarena_monitor: superuser=f bypassrls=f pg_monitor=t"
    )
    assert result.returncode == 0, result.stderr
    assert DB_PW not in argv, "parol argv-də (ps / docker inspect) görünməməlidir"
    assert "compose -f docker-compose.prod.yml exec -T postgres sh -c" in argv
    assert "-v monitor_role=emsarena_monitor" in argv
    assert stdin.startswith(f"\\set monitor_password '{DB_PW}'\n")
    for needle in (
        "SET log_statement = 'none';",
        "SET log_min_duration_statement = -1;",
        "SET log_min_error_statement = 'panic';",
        "SET pg_stat_statements.track_utility = off;",
        "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT CONNECTION LIMIT 5",
        "ALTER ROLE :\"monitor_role\" WITH PASSWORD :'monitor_password';",
        "SET default_transaction_read_only = on;",
        'GRANT pg_monitor TO :"monitor_role";',
        "Refusing unsafe monitor role",
    ):
        assert needle in stdin, needle
    # Log susdurma ALTER ROLE … PASSWORD-dan ƏVVƏL olmalıdır.
    assert stdin.index("SET log_statement") < stdin.index("WITH PASSWORD")
    assert DB_PW not in result.stdout + result.stderr
    assert "pg_monitor=t" in result.stdout


@pytest.mark.parametrize(
    "dotenv,extra_env",
    [
        (_DOTENV.replace("APP_DATABASE_USER=emsarena_app", "APP_DATABASE_USER=x") + "MONITOR_DB_USER=owner\n", {}),
        (_DOTENV, {"MONITOR_DB_USER": "emsarena_app"}),
        (_DOTENV, {"MONITOR_DB_USER": "postgres"}),
        (_DOTENV, {"MONITOR_DB_USER": "bad;name"}),
        ("POSTGRES_USER=owner\nMONITOR_DB_PASSWORD=bad'pw-with-quote-0123456789\n", {}),
        ("POSTGRES_USER=owner\nMONITOR_DB_PASSWORD=short\n", {}),
    ],
)
def test_provision_refuses_unsafe_configuration_before_touching_the_database(tmp_path, dotenv, extra_env):
    result, argv, _ = _run_provision(tmp_path, dotenv, **extra_env)
    assert result.returncode == 1
    assert argv == ""
    assert "pw-with-quote" not in result.stdout + result.stderr


def test_provision_is_a_noop_without_a_password(tmp_path):
    result, argv, _ = _run_provision(tmp_path, "POSTGRES_USER=owner\n")
    assert result.returncode == 0, result.stderr
    assert argv == "" and "not provisioned" in result.stdout


def test_provision_failure_output_is_masked(tmp_path):
    result, _, _ = _run_provision(tmp_path, _DOTENV, docker_rc=3, docker_out=f"ERROR: something about {DB_PW}")
    assert result.returncode == 1
    assert DB_PW not in result.stdout + result.stderr
    assert "something about ***" in result.stderr


def test_provision_script_static_hygiene():
    text = _read(PROVISION)
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "set -euo pipefail" in text and os.access(PROVISION, os.X_OK)
    assert "set -x" not in code and "xtrace" not in code
    assert "PGPASSWORD" not in code
    assert "-v monitor_password" not in code and "-e MONITOR_DB_PASSWORD" not in code
    subprocess.run(["bash", "-n", str(PROVISION)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", str(PROVISION)], check=True)


# ── remote_deploy.sh: preflight / activate (saxta docker) ──────────────────────


def _function_body(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", _read(DEPLOY), flags=re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


_DEPLOY_FUNCS = (
    "dotenv_value",
    "_monitor_secret_is_safe",
    "preflight_monitor_credentials",
    "_pgbouncer_stats_user_ready",
    "_redis_monitor_user_ready",
    "activate_monitor_credentials",
)
_SHOW = (
    'printf "STATE=%s/%s\\n" "$MONITOR_DB_STATE" "$REDIS_MONITOR_STATE"\n'
    "env | grep -E '^(MONITOR_DB_USER|MONITOR_DB_PASSWORD|REDIS_MONITOR_PASSWORD)=' | sort | sed 's/^/ENV:/'\n"
)


def _run_deploy(tmp_path: Path, dotenv: str, body: str, **extra_env: str) -> subprocess.CompletedProcess:
    _need("bash")
    (tmp_path / ".env").write_text(dotenv, encoding="utf-8")
    script_dir = tmp_path / "scripts/deploy"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "provision_monitor_role.sh").write_text(
        '#!/usr/bin/env bash\necho "provision user=${MONITOR_DB_USER}"\nexit "${FAKE_PROVISION_RC:-0}"\n',
        encoding="utf-8",
    )
    harness = (
        "set -euo pipefail\n"
        + "".join(_function_body(name) for name in _DEPLOY_FUNCS)
        + 'docker() { printf "%s\\n" "$*" >>"$DOCKER_LOG"; case "$*" in\n'
        + '  *"exec -T pgbouncer"*) return "${FAKE_PGB_RC:-0}" ;;\n'
        + '  *"exec -T redis"*) printf "%b" "${FAKE_REDIS_USERS:-}"; return 0 ;;\n'
        + "esac; }\n"
        + "sleep() { :; }\n"
        + f"APP_DIR={json.dumps(str(tmp_path))}\nDOCKER_LOG={json.dumps(str(tmp_path / 'docker.log'))}\n"
        + "COMPOSE_FILE=docker-compose.prod.yml\nMONITOR_DB_STATE=off\nREDIS_MONITOR_STATE=off\n"
        + body
        + _SHOW
    )
    return subprocess.run(
        ["bash", "-c", harness], capture_output=True, text=True, env={**_base_env(tmp_path), **extra_env}
    )


_FULL_DOTENV = f"POSTGRES_USER=owner\nAPP_DATABASE_USER=emsarena_app\nMONITOR_DB_PASSWORD={DB_PW}\nREDIS_MONITOR_PASSWORD={REDIS_PW}\n"


def test_deploy_preflight_without_keys_exports_empty_overrides(tmp_path):
    result = _run_deploy(
        tmp_path, "POSTGRES_USER=owner\nMONITOR_DB_USER=emsarena_monitor\n", "preflight_monitor_credentials\n"
    )
    assert result.returncode == 0, result.stderr
    assert "STATE=off/off" in result.stdout
    # .env-dəki tək MONITOR_DB_USER (parolsuz) də neytrallaşdırılır.
    for line in ("ENV:MONITOR_DB_USER=", "ENV:MONITOR_DB_PASSWORD=", "ENV:REDIS_MONITOR_PASSWORD="):
        assert line in result.stdout.splitlines()


def test_deploy_preflight_with_valid_keys_marks_pending_and_defaults_the_user(tmp_path):
    result = _run_deploy(tmp_path, _FULL_DOTENV, "preflight_monitor_credentials\n")
    assert result.returncode == 0, result.stderr
    assert "STATE=pending/pending" in result.stdout
    assert "ENV:MONITOR_DB_USER=emsarena_monitor" in result.stdout.splitlines()
    assert DB_PW not in result.stdout + result.stderr and REDIS_PW not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "dotenv",
    [
        _FULL_DOTENV + "MONITOR_DB_USER=owner\n",
        _FULL_DOTENV + "MONITOR_DB_USER=emsarena_app\n",
        _FULL_DOTENV.replace(DB_PW, "short").replace(REDIS_PW, "bad pass word 0123456789"),
    ],
)
def test_deploy_preflight_falls_back_on_unsafe_values(tmp_path, dotenv):
    result = _run_deploy(tmp_path, dotenv, "preflight_monitor_credentials\n")
    assert result.returncode == 0, result.stderr
    state = next(line for line in result.stdout.splitlines() if line.startswith("STATE="))
    assert state.startswith("STATE=off/")
    assert "ENV:MONITOR_DB_USER=" in result.stdout.splitlines()
    assert "ENV:MONITOR_DB_PASSWORD=" in result.stdout.splitlines()


def test_deploy_activate_success_keeps_monitor_credentials(tmp_path):
    result = _run_deploy(
        tmp_path,
        _FULL_DOTENV,
        "preflight_monitor_credentials\nactivate_monitor_credentials\n",
        FAKE_REDIS_USERS="default\\nmonitor\\n",
    )
    assert result.returncode == 0, result.stderr
    assert "provision user=emsarena_monitor" in result.stdout
    assert "STATE=active/active" in result.stdout
    assert "ENV:MONITOR_DB_USER=emsarena_monitor" in result.stdout.splitlines()
    calls = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert "exec -T pgbouncer sh -c" in calls and "stats_users" in calls
    assert "exec -T redis redis-cli --no-auth-warning ACL USERS" in calls
    assert DB_PW not in calls and REDIS_PW not in calls


@pytest.mark.parametrize(
    "extra_env",
    [
        {"FAKE_PROVISION_RC": "1"},  # rol yaradılmadı
        {"FAKE_PGB_RC": "3"},  # pgbouncer stats_users-də yoxdur
        {"FAKE_PGB_RC": "1"},  # pgbouncer heç vaxt hazır olmadı (30 cəhd)
    ],
)
def test_deploy_activate_db_failure_falls_back_to_the_owner_login(tmp_path, extra_env):
    result = _run_deploy(
        tmp_path,
        _FULL_DOTENV,
        "preflight_monitor_credentials\nactivate_monitor_credentials\n",
        FAKE_REDIS_USERS="default\\nmonitor\\n",
        **extra_env,
    )
    assert result.returncode == 0, result.stderr
    assert "STATE=off/active" in result.stdout
    assert "ENV:MONITOR_DB_USER=" in result.stdout.splitlines()
    assert "ENV:MONITOR_DB_PASSWORD=" in result.stdout.splitlines()
    assert "fall back to the owner login" in result.stderr


@pytest.mark.parametrize("users", ["default\\n", ""], ids=["acl-user-missing", "redis-never-answers"])
def test_deploy_activate_redis_failure_falls_back_to_the_main_password(tmp_path, users):
    result = _run_deploy(
        tmp_path,
        _FULL_DOTENV,
        "preflight_monitor_credentials\nactivate_monitor_credentials\n",
        FAKE_REDIS_USERS=users,
    )
    assert result.returncode == 0, result.stderr
    assert "STATE=active/off" in result.stdout
    assert "ENV:REDIS_MONITOR_PASSWORD=" in result.stdout.splitlines()
    assert "falls back to the main password" in result.stderr


def test_deploy_wires_monitor_credentials_around_the_first_infra_up():
    body = _function_body("docker_deploy")
    assert (
        body.index("preflight_monitor_credentials")
        < body.index("up -d postgres redis pgbouncer postgres-backup")
        < body.index("activate_monitor_credentials")
        < body.index("/app/docker/release.sh")
        < body.index("--remove-orphans")
    )
    # Heç bir monitor addımı deploy-u dayandırmır (exit yoxdur).
    for name in ("preflight_monitor_credentials", "activate_monitor_credentials"):
        assert "exit" not in _function_body(name), name


# ── prod-secrets-generate.yml ──────────────────────────────────────────────────


def _workflow() -> dict:
    return yaml.safe_load(_read(WORKFLOW))


def test_secrets_workflow_shape():
    doc = _workflow()
    on = doc.get(True, doc.get("on"))
    assert set(on) == {"workflow_dispatch"}
    inputs = on["workflow_dispatch"]["inputs"]
    assert inputs["key"]["type"] == "choice"
    assert inputs["key"]["options"] == ["MONITOR_DB_PASSWORD", "REDIS_MONITOR_PASSWORD"]
    assert inputs["redeploy"]["type"] == "boolean"
    assert doc["permissions"] == {}
    assert doc["concurrency"]["group"] == "production-deploy"
    job = doc["jobs"]["generate"]
    assert job["runs-on"] == ["self-hosted"] and job["environment"] == "production"
    assert job["env"]["TARGET_KEY"] == "${{ inputs.key }}"


_PRINT = re.compile(r"\b(echo|printf)\b")
_SECRET_REF = re.compile(r"\$\{?(value|secret|password|[A-Z_]*PASSWORD)\b", re.IGNORECASE)


def test_secrets_workflow_never_prints_or_stores_the_value_outside_dotenv():
    for step in _workflow()["jobs"]["generate"]["steps"]:
        script = step.get("run") or ""
        assert "set -x" not in script and "xtrace" not in script, step["name"]
        for line in script.splitlines():
            code = line.split(" #", 1)[0]
            if _PRINT.search(code):
                assert not _SECRET_REF.search(code), f"{step['name']}: {line.strip()}"
            if "/dev/urandom" in code:
                assert code.rstrip().endswith(">> .env"), "sirr birbaşa .env-ə yazılmalıdır"
            if re.search(r"\bcat\b[^|]*\.env\b", code):
                raise AssertionError(f".env çap olunur: {line.strip()}")
            if "CONNECTION_STRING" in code:
                assert "sed -nE" in code and code.rstrip().endswith("p')\""), "uyğun gəlməyən sətir çap olunmamalıdır"
    generate = _workflow()["jobs"]["generate"]["steps"][0]["run"]
    assert generate.index("umask 077") < generate.index("/dev/urandom")
    assert generate.index('cp .env ".env.bak.') < generate.index("/dev/urandom")


def _run_generate(tmp_path: Path, key: str) -> subprocess.CompletedProcess:
    _need("bash")
    script = _workflow()["jobs"]["generate"]["steps"][0]["run"]
    return subprocess.run(
        ["bash", "-e", "-c", script],
        capture_output=True,
        text=True,
        env={**_base_env(tmp_path), "APP_DIR": str(tmp_path), "TARGET_KEY": key},
    )


def _dotenv_values(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)


def test_secrets_workflow_generates_once_and_never_echoes_the_value(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=owner\nMONITOR_DB_PASSWORD=\n", encoding="utf-8")
    env_file.chmod(0o644)
    result = _run_generate(tmp_path, "MONITOR_DB_PASSWORD")
    assert result.returncode == 0, result.stderr
    values = _dotenv_values(env_file)
    secret = values["MONITOR_DB_PASSWORD"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", secret)
    assert values["MONITOR_DB_USER"] == "emsarena_monitor" and values["POSTGRES_USER"] == "owner"
    assert env_file.read_text(encoding="utf-8").count("MONITOR_DB_PASSWORD=") == 1
    assert secret not in result.stdout + result.stderr
    assert "MONITOR_DB_PASSWORD: generated" in result.stdout
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    backups = list(tmp_path.glob(".env.bak.*"))
    assert len(backups) == 1 and secret not in backups[0].read_text(encoding="utf-8")

    again = _run_generate(tmp_path, "MONITOR_DB_PASSWORD")
    assert again.returncode == 0, again.stderr
    assert "MONITOR_DB_PASSWORD: already present" in again.stdout
    assert "MONITOR_DB_USER: already present" in again.stdout
    assert _dotenv_values(env_file)["MONITOR_DB_PASSWORD"] == secret

    redis = _run_generate(tmp_path, "REDIS_MONITOR_PASSWORD")
    assert redis.returncode == 0, redis.stderr
    redis_secret = _dotenv_values(env_file)["REDIS_MONITOR_PASSWORD"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", redis_secret) and redis_secret != secret
    assert redis_secret not in redis.stdout + redis.stderr
    assert "MONITOR_DB_USER" not in redis.stdout


def test_secrets_workflow_rejects_unknown_keys(tmp_path):
    (tmp_path / ".env").write_text("POSTGRES_USER=owner\n", encoding="utf-8")
    result = _run_generate(tmp_path, "SECRET_KEY")
    assert result.returncode != 0
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "POSTGRES_USER=owner\n"


def test_prod_smoke_proves_the_proxy_is_get_only_and_logs_still_reach_loki():
    workflow = yaml.safe_load(_read(ROOT / ".github/workflows/_prod-smoke.yml"))
    steps = {step["name"]: step for step in workflow["jobs"]["prod-smoke"]["steps"]}
    run = next(step["run"] for name, step in steps.items() if "docker-socket-proxy" in name)
    assert "http://127.0.0.1:2375/containers/json" in run
    assert "--post-data='{}' http://127.0.0.1:2375/containers/create" in run and "accepted a POST" in run
    assert "http://127.0.0.1:2375/info" in run
    assert "docker\\.sock" in run and "loki:3100/loki/api/v1/label/container/values" in run


# ── prod_audit.sh: ✅/⚠️ sətirləri, sirr çap olunmur ────────────────────────────


def test_prod_audit_reports_exporter_logins_and_promtail_socket_without_secrets():
    text = _read(PROD_AUDIT)
    section = text[text.index('section "4a.') : text.index('section "5.')]
    for needle in (
        "cenv postgres_exporter DATA_SOURCE_USER",
        "cenv redis_exporter REDIS_USER",
        "docker\\.sock",
        "cenv docker-socket-proxy POST",
        "stats_users",
        "ACL USERS",
    ):
        assert needle in section, needle
    assert section.count("ok ") >= 5 and section.count("warn ") >= 5
    # Sirr açarları yalnız «var/yoxdur» kimi yoxlanır; connection string-dən yalnız istifadəçi.
    for line in section.splitlines():
        if "dotenv MONITOR_DB_PASSWORD" in line or "dotenv REDIS_MONITOR_PASSWORD" in line:
            assert '[ -n "$(dotenv ' in line
        if "CONNECTION_STRING" in line:
            assert "sed -nE" in line
    assert not re.search(r"cenv \S+ (DATA_SOURCE_PASS|REDIS_PASSWORD|MONITOR_DB_PASSWORD)\b", section)
    subprocess.run(["bash", "-n", str(PROD_AUDIT)], check=True)
