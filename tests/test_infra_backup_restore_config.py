"""
Backup/DR və DB monitorinq qapıları (audit 2026-09-28: AD-01, AD-02, AD-03,
AD-04, AD-05, DB-02, DB-08).

DB-siz: repo fayllarını oxuyur (compose YAML, Prometheus qaydaları, runbook) və
host skriptlərini (restore_drill.sh, offsite_backup.sh) yalnız bağlantıdan ƏVVƏLKİ
yollarda — konfiqurasiya yoxdur / təhlükəli ad — işlədir. Məqsəd düzəlişlərin
geri sürüşməsinin qarşısını almaqdır.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROD_COMPOSE = ROOT / "docker-compose.prod.yml"
AGENT_COMPOSE = ROOT / "docker-compose.agent.yml"
ALERTS = ROOT / "docker/prometheus/alerts.yml"
DEPLOYMENT_MD = ROOT / "docs/operations/deployment.md"
SANDBOX_MD = ROOT / "docs/operations/CLAUDE_POSTGRES_SANDBOX.md"
RESTORE_DRILL = ROOT / "scripts/ops/restore_drill.sh"
OFFSITE_BACKUP = ROOT / "scripts/ops/offsite_backup.sh"
OFFSITE_METRIC = "emsarena_offsite_backup_last_success_timestamp_seconds"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _alerts() -> dict[str, dict]:
    rules = {}
    for group in _yaml(ALERTS)["groups"]:
        for rule in group["rules"]:
            if "alert" in rule:
                rules[rule["alert"]] = rule
    return rules


def _section(text: str, heading: str) -> str:
    """`heading`-dən növbəti eyni/yuxarı səviyyəli başlığa qədər mətn (kod bloklarındakı `#` şərhləri sayılmır)."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text[text.index(heading) :].splitlines()
    out, in_code = [lines[0]], False
    for line in lines[1:]:
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(rf"^#{{1,{level}}} ", line):
            break
        out.append(line)
    return "\n".join(out)


# ── AD-03: agent sandbox yalnız loopback, parol məcburi ─────────────────────
def test_agent_sandbox_ports_bind_to_loopback_only():
    services = _yaml(AGENT_COMPOSE)["services"]
    for name in ("postgres", "redis"):
        ports = services[name]["ports"]
        assert ports, name
        for mapping in ports:
            assert str(mapping).startswith("127.0.0.1:"), f"{name}: {mapping} LAN-a açıqdır"


def test_agent_sandbox_password_is_required_and_not_committed():
    raw = AGENT_COMPOSE.read_text(encoding="utf-8")
    assert "emsarena_agent_password" not in raw
    assert "AGENT_POSTGRES_PASSWORD:-" not in raw, "parol üçün defolt dəyər qalmamalıdır"
    env = _yaml(AGENT_COMPOSE)["services"]["postgres"]["environment"]
    assert env["POSTGRES_PASSWORD"].startswith("${AGENT_POSTGRES_PASSWORD:?")
    assert "emsarena_agent_password" not in SANDBOX_MD.read_text(encoding="utf-8")


# ── AD-05 / AD-04: build arg və sahib açarları ──────────────────────────────
def test_prod_build_passes_apt_security_refresh():
    args = _yaml(PROD_COMPOSE)["x-app-build"]["args"]
    assert args["APT_SECURITY_REFRESH"] == "${APT_SECURITY_REFRESH:-manual}"


@pytest.mark.parametrize(
    "name",
    [
        "AI_ASSISTANT_ENABLED",
        "AI_ASSISTANT_LOG_MAX_CHARS",
        "AI_ASSISTANT_LOG_RETENTION_DAYS",
        "PUBLIC_SIGNUP_ENABLED",
        "FINAL_EXAM_PIN_MAX_FAILURES",
        "FINAL_EXAM_PIN_LOCK_MINUTES",
        "FINAL_EXAM_ENTRY_RATE_PER_MINUTE",
    ],
)
def test_documented_owner_switches_reach_every_app_container(name):
    data = _yaml(PROD_COMPOSE)
    assert name in data["x-app-env"]
    for service in ("app", "celery_worker", "celery_worker_heavy", "celery_beat"):
        assert name in data["services"][service]["environment"], service


# ── DB-02: log/pooler parametrləri (server səviyyəli statement_timeout YOX) ──
def test_postgres_logs_slow_queries_and_lock_waits_without_global_statement_timeout():
    command = _yaml(PROD_COMPOSE)["services"]["postgres"]["command"]
    flags = [item for item in command if isinstance(item, str) and "=" in item]
    assert "log_lock_waits=on" in flags
    assert "deadlock_timeout=1s" in flags
    assert any(flag.startswith("log_min_duration_statement=") for flag in flags)
    assert not any(flag.startswith("statement_timeout=") for flag in flags)


def test_pgbouncer_bounds_client_queue_wait():
    env = _yaml(PROD_COMPOSE)["services"]["pgbouncer"]["environment"]
    assert env["QUERY_WAIT_TIMEOUT"] == "${PGBOUNCER_QUERY_WAIT_TIMEOUT:-15}"


# ── AD-01 / DB-08: textfile kollektoru və alertlər ─────────────────────────
def test_node_exporter_reads_host_textfile_directory_through_rootfs_mount():
    node = _yaml(PROD_COMPOSE)["services"]["node_exporter"]
    assert "/:/host:ro" in node["volumes"]
    flag = "--collector.textfile.directory=/host/var/lib/node_exporter/textfile_collector"
    assert flag in node["command"]
    # skriptin defolt qovluğu ilə eyni olmalıdır (host yolu = /host altındakı yol)
    script = OFFSITE_BACKUP.read_text(encoding="utf-8")
    assert "/var/lib/node_exporter/textfile_collector" in script


def test_offsite_alerts_cover_stale_never_and_missing_metric():
    rules = _alerts()
    stale = rules["OffsiteBackupStale"]
    assert OFFSITE_METRIC in stale["expr"] and "26 * 3600" in stale["expr"]
    assert stale["labels"]["severity"] == "critical"
    assert f"absent({OFFSITE_METRIC})" in rules["OffsiteBackupMetricMissing"]["expr"]
    assert "emsarena_offsite_backup_last_run_success" in rules["OffsiteBackupLastRunFailed"]["expr"]
    assert OFFSITE_METRIC in OFFSITE_BACKUP.read_text(encoding="utf-8")


def test_database_tier_alerts_use_metrics_the_exporters_expose():
    rules = _alerts()
    assert "pgbouncer_pools_client_waiting_connections" in rules["PgBouncerClientsWaiting"]["expr"]
    assert "pgbouncer_pools_client_maxwait_seconds" in rules["PgBouncerMaxWaitHigh"]["expr"]
    assert "pg_stat_database_deadlocks" in rules["PostgresDeadlocks"]["expr"]
    assert "pg_stat_activity_max_tx_duration" in rules["PostgresLongTransaction"]["expr"]
    assert "max_connections=200" not in rules["PgConnectionsHigh"]["annotations"]["description"]


# ── AD-02: runbook yeni bazaya bərpa edir, düzgün servis adları ─────────────
def test_restore_runbook_never_pipes_into_the_live_database():
    text = DEPLOYMENT_MD.read_text(encoding="utf-8")
    for heading in ("### Restore procedure", "### Database rollback"):
        section = _section(text, heading)
        assert '-d "$POSTGRES_DB"' not in section, f"{heading}: canlı bazaya bərpa"
    restore = _section(text, "### Restore procedure")
    assert "restore_drill.sh --keep" in restore
    assert "ALTER DATABASE" in restore and "RENAME" in restore
    assert "ON_ERROR_STOP=1" in restore


def test_runbook_compose_commands_use_existing_service_names():
    services = set(_yaml(PROD_COMPOSE)["services"])
    text = DEPLOYMENT_MD.read_text(encoding="utf-8")
    joined = text.replace("\\\n", " ")
    for line in joined.splitlines():
        match = re.search(r"docker compose -f docker-compose\.prod\.yml (stop|up -d)(.*)$", line)
        if not match:
            continue
        tail = re.split(r"`| #", match.group(2), maxsplit=1)[0]
        names = [tok for tok in tail.split() if not tok.startswith("-") and "=" not in tok]
        names = [tok for tok in names if re.fullmatch(r"[a-z][a-z0-9_-]*", tok)]
        unknown = [tok for tok in names if tok not in services]
        assert not unknown, f"naməlum servis(lər) {unknown}: {line.strip()}"


# ── Skriptlər (bağlantısız yollar) ──────────────────────────────────────────
@pytest.mark.parametrize("script", [RESTORE_DRILL, OFFSITE_BACKUP])
def test_ops_scripts_are_valid_strict_bash(script):
    text = script.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert os.access(script, os.X_OK), f"{script.name} icra oluna bilən deyil"
    subprocess.run(["bash", "-n", str(script)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", str(script)], check=True)


def test_offsite_backup_unconfigured_writes_zero_metric_and_fails(tmp_path):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "OFFSITE_ENV_FILE": str(tmp_path / "absent.env"),
        "OFFSITE_TEXTFILE_DIR": str(tmp_path / "textfile"),
        "OFFSITE_LOG": str(tmp_path / "offsite.log"),
    }
    result = subprocess.run(["bash", str(OFFSITE_BACKUP)], env=env, capture_output=True, text=True)
    assert result.returncode == 3, result.stderr
    assert "NOT CONFIGURED" in result.stderr
    metrics = (tmp_path / "textfile" / "emsarena_offsite_backup.prom").read_text()
    assert f"{OFFSITE_METRIC} 0\n" in metrics
    assert "emsarena_offsite_backup_configured 0\n" in metrics


def test_restore_drill_rejects_unsafe_scratch_db_name_before_connecting(tmp_path):
    dump = tmp_path / "toy.sql.gz"
    with gzip.open(dump, "wt") as fh:
        fh.write("SELECT 1;\n")
    result = subprocess.run(
        ["bash", str(RESTORE_DRILL), "--dsn", "postgres://nobody@127.0.0.1:1/postgres", "--db", "x; drop", str(dump)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unsafe scratch DB name" in result.stderr
