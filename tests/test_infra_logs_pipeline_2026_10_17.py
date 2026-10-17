"""Mərkəzi log zənciri qapıları — sahib 2026-10-17: «Sistem monitorinqində loglar boş göstərir».

Zəncir: promtail (docker_sd) → docker-socket-proxy → dockerd → promtail → Loki ← Django
(``apps/monitoring/logs.py``). Repo faylları oxunur (PyYAML / regex):

* Django-nun Loki URL-i (settings defoltu ↔ compose env defoltu) eynidir və Loki həmin
  şəbəkədədir; UI-ın defolt seçicisi promtail-in qoyduğu etiketlərə uyğundur;
* promtail docker_sd proxy üzərindən, proxy yalnız GET + /containers;
* Loki tək-replika, ``inmemory`` ring — CI prod-smoke logundakı
  ``recalculate_owned_streams … "zone not set"`` zərərsizdir (zone-awareness yoxdur,
  ingestion işləyir; eyni image + konfiqlə lokal və CI-da sınanıb);
* ``LogIngestionStalled`` alerti göndərmə qırılanda yanır (səssiz boş tabın qarşısı);
* ``prod-audit.yml`` ``scope=logs`` diaqnostikası oxu-yalnızdır və log MƏZMUNU çap etmir.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.prod.yml"
PROMTAIL = ROOT / "docker/promtail/promtail-config.yml"
LOKI = ROOT / "docker/loki/loki-config.yml"
ALERTS = ROOT / "docker/prometheus/alerts.yml"
PROMETHEUS = ROOT / "docker/prometheus/prometheus.yml"
INTEGRATIONS = ROOT / "config/settings/components/integrations.py"
AUDIT_WORKFLOW = ROOT / ".github/workflows/prod-audit.yml"
DIAG = ROOT / "scripts/ops/prod_logs_diag.sh"
PROBE = ROOT / "scripts/ops/prod_logs_probe.py"
AUDIT = ROOT / "scripts/ops/prod_audit.sh"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_django_loki_url_default_matches_compose_and_loki_network():
    settings_default = re.search(
        r'MONITORING_LOKI_URL = os\.getenv\("MONITORING_LOKI_URL", "([^"]+)"\)', INTEGRATIONS.read_text()
    )
    assert settings_default, "MONITORING_LOKI_URL settings-də env-dən oxunmalıdır"
    compose_text = COMPOSE.read_text(encoding="utf-8")
    assert f"MONITORING_LOKI_URL: ${{MONITORING_LOKI_URL:-{settings_default.group(1)}}}" in compose_text
    assert settings_default.group(1) == "http://loki:3100"
    services = _compose()["services"]
    assert "emsarena-network" in services["loki"]["networks"]
    assert "emsarena-network" in services["app"]["networks"]


def test_promtail_labels_match_the_ui_selector_and_ship_to_loki():
    from apps.monitoring.logs import DEFAULT_SELECTOR, build_logql

    config = yaml.safe_load(PROMTAIL.read_text(encoding="utf-8"))
    assert config["clients"][0]["url"] == "http://loki:3100/loki/api/v1/push"
    job = next(item for item in config["scrape_configs"] if item["job_name"] == "docker")
    assert job["docker_sd_configs"][0]["host"] == "tcp://docker-socket-proxy:2375"
    relabels = {rule.get("target_label"): rule for rule in job["relabel_configs"]}
    assert relabels["job"]["replacement"] == "docker"
    assert relabels["container"]["source_labels"] == ["__meta_docker_container_name"]
    assert relabels["service"]["source_labels"] == ["__meta_docker_container_label_com_docker_compose_service"]
    assert DEFAULT_SELECTOR == '{job="docker"}'
    assert build_logql("emsarena-nginx") == '{container="emsarena-nginx"}'


def test_promtail_reaches_docker_only_through_the_get_only_proxy():
    services = _compose()["services"]
    promtail, proxy = services["promtail"], services["docker-socket-proxy"]
    assert not any("docker.sock" in str(volume) for volume in promtail.get("volumes", []))
    assert set(promtail["networks"]) == {"emsarena-network", "docker-api"}
    assert proxy["networks"] == ["docker-api"]
    env = proxy["environment"]
    assert env["CONTAINERS"] == "1" and env["POST"] == "0"


def test_single_binary_loki_needs_no_zone_awareness():
    config = yaml.safe_load(LOKI.read_text(encoding="utf-8"))
    common = config["common"]
    assert common["replication_factor"] == 1
    assert common["ring"]["kvstore"]["store"] == "inmemory"
    # Zone-awareness konfiqurasiya olunmayıb → «zone not set» yalnız owned-streams sayğacının
    # xəbərdarlığıdır (ingestion/sorğu işləyir). Kimsə zona əlavə etsə, hamısına eyni etməlidir.
    assert "zone_awareness_enabled" not in LOKI.read_text(encoding="utf-8")
    assert config["limits_config"]["max_query_lookback"] == "336h"


def test_log_ingestion_stalled_alert_uses_loki_metric_that_prometheus_scrapes():
    groups = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))["groups"]
    rules = {rule["alert"]: rule for group in groups for rule in group["rules"] if "alert" in rule}
    rule = rules["LogIngestionStalled"]
    assert "loki_distributor_lines_received_total" in rule["expr"]
    assert "[1h]" in rule["expr"]
    assert rule["labels"]["severity"] == "warning"
    assert "scope=logs" in rule["annotations"]["description"]
    prometheus = yaml.safe_load(PROMETHEUS.read_text(encoding="utf-8"))
    loki_job = next(job for job in prometheus["scrape_configs"] if job["job_name"] == "emsarena-loki")
    assert loki_job["static_configs"][0]["targets"] == ["loki:3100"]

    from apps.monitoring.wording import alert_title

    assert alert_title("LogIngestionStalled") != alert_title("__unknown__")


def test_prod_audit_has_a_logs_only_scope_passed_through_env():
    workflow = yaml.safe_load(AUDIT_WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get("on") or workflow.get(True)
    scope = triggers["workflow_dispatch"]["inputs"]["scope"]
    assert scope["type"] == "choice" and scope["options"] == ["full", "logs"] and scope["default"] == "full"
    step = next(step for step in workflow["jobs"]["audit"]["steps"] if step.get("name") == "🔎 Audit")
    assert step["env"]["AUDIT_SCOPE"] == "${{ inputs.scope || 'full' }}"
    assert "${{" not in step["run"], "input run: blokuna birbaşa interpolasiya olunmamalıdır (env ilə)"
    assert "prod_logs_diag.sh" in step["run"]
    assert workflow["permissions"] == {"contents": "read"}
    assert '. "$AUDIT_DIR/prod_logs_diag.sh"' in AUDIT.read_text(encoding="utf-8")


def test_logs_diagnostics_are_read_only_and_print_no_log_content():
    diag = DIAG.read_text(encoding="utf-8")
    probe = PROBE.read_text(encoding="utf-8")
    for forbidden in ("docker restart", "docker stop", "docker rm", "compose up", "compose restart", "-X POST"):
        assert forbidden not in diag, forbidden
    assert "prod_logs_probe.py" in diag
    # promtail/Loki/proxy-nin öz logundan yalnız msg="…" mətni sayılır.
    assert 'grep -oE \'msg="[^"]{0,140}"\'' in diag
    assert "requests.post" not in probe and ".post(" not in probe
    # Log axını dəyərlərindən yalnız zaman damğası (value[0]) oxunur — sətir mətni (value[1]) yox.
    assert "value[0]" in probe
    assert "value[1]" not in probe
