"""Monitorinq yükünün azaldılması + pauza qapıları — sahib 2026-10-21.

«Sistemin yüklənməsində əsas yüklərdən biri monitorinqə görə ola bilər — əgər sistemi çox yükləsə, onu
söndürmək də olsun. Və onun performans optimizasiyasını nəzərə al.» Repo faylları oxunur (PyYAML / regex /
``bash -n`` / saxta ``docker`` ilə dry-run):

* Prometheus 30 s scrape/qiymətləndirmə; monitorinq stekinin öz metrikləri `keep` siyahısı ilə kəsilir — amma
  alertlərin, Grafana-nın, Monitorinq səhifəsinin və prod-audit skriptlərinin oxuduğu HƏR ailə saxlanılır;
* pauza markeri yalnız qəsdən dayanan cadvisor/loki hədəflərini susdurur (app/DB/… TargetDown həmişə yanır);
* promtail: 60 s refresh, 5 s partiya, oxu sürəti tavanı və yalnız UĞURLU health/scrape sətirlərinin atılması;
* ``prod-host-maint.yml`` ``monitoring-pause`` (confirm=PAUSE) / ``monitoring-resume`` skripti: yalnız icazəli
  servislər, prometheus/alertmanager/exporterlər/blackbox heç vaxt dayanmır; deploy markeri silir.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS = ROOT / "docker/prometheus/prometheus.yml"
ALERTS = ROOT / "docker/prometheus/alerts.yml"
PROMTAIL = ROOT / "docker/promtail/promtail-config.yml"
DASHBOARD = ROOT / "docker/grafana/dashboards/emsarena-overview.json"
WORKFLOW = ROOT / ".github/workflows/prod-host-maint.yml"
PAUSE_SCRIPT = ROOT / "scripts/ops/monitoring_pause.sh"
DEPLOY = ROOT / "scripts/deploy/remote_deploy.sh"
COMPOSE = ROOT / "docker-compose.prod.yml"
DOC = ROOT / "docs/operations/SISTEM_MONITORINQI.md"

#: Metrik ailəsini istifadə edən mənbələr (alert, panel, Django sorğuları, prod-audit / log diaqnostikası).
METRIC_SOURCES = [
    ALERTS,
    DASHBOARD,
    *sorted((ROOT / "apps/monitoring").glob("*.py")),
    ROOT / "scripts/ops/prod_audit.sh",
    ROOT / "scripts/ops/prod_logs_probe.py",
]
#: Metrik adına oxşayan, amma metrik olmayan sözlər (volume, URL adı, açar adı, Loki marşrutu).
NOT_METRICS = {
    "alertmanager_data",
    "alertmanager_webhook",
    "container_restarts_24h",
    "container_memory_usage_bytes",  # alerts.yml-də yalnız ŞƏRHDƏ («page cache sayır — işlətməyin»)
    "loki_api_v1_query_range",  # Loki marşrut adı (route=~...), metrik deyil
    "loki_data",
    "prometheus_client",
    "prometheus_data",
    "prometheus_ok",
}
JOB_PREFIXES = {
    "emsarena-cadvisor": "container_",
    "emsarena-prometheus": "prometheus_",
    "emsarena-alertmanager": "alertmanager_",
    "emsarena-loki": "loki_",
}
PAUSABLE = {"cadvisor", "promtail", "docker-socket-proxy", "loki", "grafana"}
NEVER_PAUSED = {"prometheus", "alertmanager", "node_exporter", "blackbox_exporter", "postgres_exporter", "app"}


def _prometheus() -> dict:
    return yaml.safe_load(PROMETHEUS.read_text(encoding="utf-8"))


def _jobs() -> dict:
    return {job["job_name"]: job for job in _prometheus()["scrape_configs"]}


def _rules() -> dict:
    groups = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))["groups"]
    return {rule["alert"]: rule for group in groups for rule in group["rules"] if "alert" in rule}


def _used_metrics(prefix: str) -> set[str]:
    names: set[str] = set()
    pattern = re.compile(rf"\b{re.escape(prefix)}[a-z0-9_]+\b")
    for path in METRIC_SOURCES:
        names.update(pattern.findall(path.read_text(encoding="utf-8")))
    return {name for name in names if name not in NOT_METRICS}


def test_global_scrape_and_evaluation_interval_is_30s():
    config = _prometheus()["global"]
    assert config["scrape_interval"] == "30s"
    assert config["evaluation_interval"] == "30s"
    # Ən qısa rate pəncərəsi ən azı 4 nümunə tutmalıdır (30 s × 4 = 2 dəq).
    windows = re.findall(r"rate\([^)]*\[(\d+)([smh])\]", ALERTS.read_text(encoding="utf-8"))
    seconds = [int(value) * {"s": 1, "m": 60, "h": 3600}[unit] for value, unit in windows]
    assert seconds and min(seconds) >= 120


def test_metric_keep_lists_retain_every_family_that_is_read_somewhere():
    jobs = _jobs()
    for job_name, prefix in JOB_PREFIXES.items():
        relabels = jobs[job_name]["metric_relabel_configs"]
        keep = next(r for r in relabels if r["source_labels"] == ["__name__"] and r["action"] == "keep")
        used = _used_metrics(prefix)
        assert used, job_name
        missing = sorted(name for name in used if not re.fullmatch(keep["regex"], name))
        assert not missing, f"{job_name}: istifadə olunan, amma atılan metriklər: {missing}"


def test_cadvisor_keeps_only_this_projects_containers():
    relabels = _jobs()["emsarena-cadvisor"]["metric_relabel_configs"]
    by_name = next(r for r in relabels if r["source_labels"] == ["name"])
    assert by_name["action"] == "keep"
    for name in ("emsarena-nginx", "educationmanagementstudentarena-app-3"):
        assert re.fullmatch(by_name["regex"], name)
    assert not re.fullmatch(by_name["regex"], "")
    assert not re.fullmatch(by_name["regex"], "other-stack-db-1")


def test_app_and_exporter_jobs_are_not_filtered():
    jobs = _jobs()
    for name in ("emsarena-app", "emsarena-postgres", "emsarena-node", "emsarena-redis", "emsarena-blackbox"):
        assert "metric_relabel_configs" not in jobs[name], name


def test_pause_marker_silences_only_the_paused_targets():
    rules = _rules()
    target_down = " ".join(rules["TargetDown"]["expr"].split())
    assert 'up{job!~"emsarena-cadvisor|emsarena-loki"} == 0' in target_down
    assert 'up{job=~"emsarena-cadvisor|emsarena-loki"} == 0 unless on() (max(emsarena_monitoring_paused) == 1)' in (
        target_down
    )
    container_down = " ".join(rules["ContainerDown"]["expr"].split())
    assert 'unless on() (max(emsarena_monitoring_paused) == 1 and on() max(up{job="emsarena-cadvisor"}) == 0)' in (
        container_down
    )
    stalled = " ".join(rules["LogIngestionStalled"]["expr"].split())
    assert 'max(up{job="emsarena-loki"}) == 0' in stalled
    # Kəsinti alertlərinə marker heç vaxt toxunmur.
    for name in ("PostgresDown", "RedisDown", "NginxDown", "EndpointProbeFailed", "Watchdog", "CeleryBeatStale"):
        assert "emsarena_monitoring_paused" not in rules[name]["expr"], name
    assert rules["MonitoringPausedTooLong"]["labels"]["severity"] == "warning"
    assert rules["MonitoringPauseMarkerStale"]["labels"]["severity"] == "warning"

    from apps.monitoring.wording import alert_title

    for name in ("MonitoringPausedTooLong", "MonitoringPauseMarkerStale"):
        assert alert_title(name) != alert_title("__unknown__"), name


def test_promtail_is_tuned_and_drops_only_successful_health_noise():
    config = yaml.safe_load(PROMTAIL.read_text(encoding="utf-8"))
    client = config["clients"][0]
    assert client["batchwait"] == "5s"
    limits = config["limits_config"]
    assert limits["readline_rate_enabled"] is True and limits["readline_rate_drop"] is False
    job = config["scrape_configs"][0]
    assert job["docker_sd_configs"][0]["refresh_interval"] == "60s"
    drops = [stage["drop"]["expression"] for stage in job["pipeline_stages"] if "drop" in stage]
    assert len(drops) == 2

    def dropped(line: str) -> bool:
        return any(re.search(expression, line) for expression in drops)

    daphne = '172.18.0.5:41234 - - [21/Oct/2026:06:05:00] "GET {path}" {status} 120'
    nginx = '172.18.0.9 peer=172.18.0.9 - - [21/Oct/2026:06:05:00 +0400] "GET {path} HTTP/1.1" {status} 15 "-" "{ua}"'
    assert dropped(daphne.format(path="/metrics/", status=200))
    assert dropped(daphne.format(path="/ping/", status=200))
    assert dropped(daphne.format(path="/health/", status=200))
    assert dropped(nginx.format(path="/accounts/login/", status=200, ua="Blackbox Exporter/0.25.0"))
    # Xətalar, degraded sağlamlıq və real istifadəçi sorğuları Loki-də qalır.
    assert not dropped(daphne.format(path="/health/", status=207))
    assert not dropped(daphne.format(path="/metrics/", status=500))
    assert not dropped(daphne.format(path="/exams/", status=200))
    assert not dropped(nginx.format(path="/health/", status=503, ua="Blackbox Exporter/0.25.0"))
    assert not dropped(nginx.format(path="/ping/", status=200, ua="Mozilla/5.0"))


def test_host_maint_offers_pause_and_resume_with_confirmation():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = workflow.get(True, workflow.get("on"))
    options = on["workflow_dispatch"]["inputs"]["action"]["options"]
    assert {"monitoring-pause", "monitoring-resume"} <= set(options)
    job = workflow["jobs"]["host"]
    assert "github.event.inputs.action != 'monitoring-pause' || github.event.inputs.confirm == 'PAUSE'" in job["if"]
    steps = [step for step in job["steps"] if "monitoring-pause" in str(step.get("if", ""))]
    checkout = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert checkout and checkout[0]["with"]["persist-credentials"] is False
    runs = [step for step in steps if "run" in step]
    assert len(runs) == 1
    step = runs[0]
    assert "${{" not in step["run"], "inputs run:-a interpolasiya olunmur, env ilə ötürülür"
    assert step["env"]["ACTION"] == "${{ github.event.inputs.action }}"
    assert step["env"]["CONFIRM"] == "${{ github.event.inputs.confirm }}"
    assert '[ "$CONFIRM" != "PAUSE" ]' in step["run"]
    assert "scripts/ops/monitoring_pause.sh" in step["run"]
    code = "\n".join(line for line in step["run"].splitlines() if not line.lstrip().startswith("#"))
    for needle in ("secrets.", ".env", "printenv", "set -x", "docker compose config", "docker inspect"):
        assert needle not in code, needle
    assert "monitoring_pause.prom" in job["steps"][0]["run"], "status pauza vəziyyətini göstərir"


def test_pause_script_parses_and_pauses_only_heavy_non_critical_services():
    subprocess.run(["bash", "-n", str(PAUSE_SCRIPT)], check=True)
    text = PAUSE_SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text
    defaults = re.search(r'PAUSE_SERVICES="\$\{PAUSE_SERVICES:-([^}]*)\}"', text).group(1).split()
    allowed = re.search(r'ALLOWED_SERVICES="([^"]*)"', text).group(1).split()
    assert set(defaults) == set(allowed) == PAUSABLE
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert PAUSABLE <= set(services)
    assert not (NEVER_PAUSED & set(allowed))
    assert "emsarena_monitoring_paused 1" in text and "emsarena_monitoring_paused_since_timestamp_seconds" in text


def _fake_env(tmp_path: Path) -> dict:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    docker = bin_dir / "docker"
    # Hər çağırış bir sətir (marker yazısının çoxsətirli `sh -c` arqumenti də).
    docker.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" | tr "\\n" " " >> "{log}"\necho >> "{log}"\n', encoding="utf-8")
    docker.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "APP_DIR": str(app_dir),
        "TEXTFILE_DIR": str(textfile),
        "MARKER_WAIT_SECONDS": "0",
    }


def test_pause_script_order_marker_first_then_stop(tmp_path):
    env = _fake_env(tmp_path)
    subprocess.run(["bash", str(PAUSE_SCRIPT), "pause"], check=True, env=env, capture_output=True, text=True)
    calls = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    marker = next(i for i, call in enumerate(calls) if call.startswith("run ") and "monitoring_pause.prom" in call)
    stop = next(i for i, call in enumerate(calls) if " stop " in f" {call} ")
    assert marker < stop
    assert calls[stop].split()[-5:] == ["cadvisor", "promtail", "docker-socket-proxy", "loki", "grafana"]

    (tmp_path / "docker.log").unlink()
    subprocess.run(["bash", str(PAUSE_SCRIPT), "resume"], check=True, env=env, capture_output=True, text=True)
    calls = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    up = next(i for i, call in enumerate(calls) if "up -d --no-deps" in call)
    remove = next(i for i, call in enumerate(calls) if "rm -f /tf/monitoring_pause.prom" in call)
    assert up < remove


def test_pause_script_refuses_critical_services_and_unknown_modes(tmp_path):
    env = _fake_env(tmp_path)
    for services in ("prometheus", "app", "cadvisor alertmanager"):
        result = subprocess.run(
            ["bash", str(PAUSE_SCRIPT), "pause"],
            env={**env, "PAUSE_SERVICES": services},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 65, services
    assert not (tmp_path / "docker.log").exists(), "rədd edilən çağırışda docker-ə toxunulmur"
    result = subprocess.run(["bash", str(PAUSE_SCRIPT), "stop-everything"], env=env, capture_output=True, text=True)
    assert result.returncode == 64


def test_deploy_resumes_and_clears_the_marker_after_the_full_up():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "clear_monitoring_pause_marker() {" in text
    body = text[text.index("legacy_deploy() {") :]
    full_up = body.index("up -d --remove-orphans")
    assert full_up < body.index("  clear_monitoring_pause_marker\n")


def test_runbook_documents_switches_and_pause():
    doc = DOC.read_text(encoding="utf-8")
    for needle in (
        "monitoring.in_app_enabled",
        "monitoring.auto_pause_on_load",
        "monitoring.load_pause_factor",
        "monitoring.ui_refresh_seconds",
        "action=monitoring-pause",
        "confirm=PAUSE",
        "action=monitoring-resume",
        "MonitoringPauseMarkerStale",
    ):
        assert needle in doc, needle
