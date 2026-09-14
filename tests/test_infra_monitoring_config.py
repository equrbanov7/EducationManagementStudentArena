"""Monitorinq/alert konfiqurasiya qapıları — 2026-09-13 infra auditi.

Repo faylları oxunur (PyYAML / regex): docker/prometheus/{prometheus,alerts}.yml,
docker/alertmanager/alertmanager.tmpl.yml, docker/nginx/nginx.conf,
.github/workflows/_security.yml, .trivyignore. Tapıntılar: P1-3 (deadman +
çatdırılma alerti), P2-1 (Alertmanager webhook nginx üzərindən), P2-2 (app
scrape replika-başına dns_sd), P2-8 (heavy növbə/worker qaydaları), P3-7
(.trivyignore baxış tarixi), P3-14 (backlog `for` 2m), P3-15 (advisory
`safety` addımı yoxdur).

Webhook testi auditorun reproduksiyasından (`test_alertmanager_webhook_direct_post.py`)
çevrilib: birbaşa `app:8000` çağırışı düzgün prod konfiqində 400/301 alır;
nginx-in daxili blokunun ötürdüyü başlıqlarla (Host localhost + XFP https)
isə 200.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from django.test import Client, override_settings

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ALERTS_PATH = ROOT / "docker/prometheus/alerts.yml"
PROMETHEUS_PATH = ROOT / "docker/prometheus/prometheus.yml"
ALERTMANAGER_TMPL_PATH = ROOT / "docker/alertmanager/alertmanager.tmpl.yml"
NGINX_CONF_PATH = ROOT / "docker/nginx/nginx.conf"

WEBHOOK_PATH = "/api/superadmin/monitoring/alertmanager-webhook/"


def _rules() -> dict[str, dict]:
    data = yaml.safe_load(ALERTS_PATH.read_text(encoding="utf-8"))
    return {rule["alert"]: rule for group in data["groups"] for rule in group["rules"] if "alert" in rule}


def _alertmanager_template() -> dict:
    text = ALERTMANAGER_TMPL_PATH.read_text(encoding="utf-8")
    # Placeholder-lar YAML üçün adi sətirdir (`__X__`); `repeat_interval:
    # __WATCHDOG_REPEAT__` də sətir kimi parse olunur.
    return yaml.safe_load(text)


def _nginx_location_block(prefix: str) -> str:
    conf = NGINX_CONF_PATH.read_text(encoding="utf-8")
    start = conf.index(prefix)
    depth = 0
    for index in range(start, len(conf)):
        if conf[index] == "{":
            depth += 1
        elif conf[index] == "}":
            depth -= 1
            if depth == 0:
                return conf[start : index + 1]
    raise AssertionError(f"nginx bloku bağlanmır: {prefix}")


# ── P1-3 — monitorinqin öz sağlamlığı ─────────────────────────────────────


def test_watchdog_rule_always_fires_and_is_routed_to_a_dedicated_heartbeat_receiver():
    rules = _rules()
    assert "Watchdog" in rules, "P1-3: deadman `Watchdog` qaydası yoxdur"
    assert rules["Watchdog"]["expr"].strip() == "vector(1)"
    assert "for" not in rules["Watchdog"], "Watchdog dərhal yanmalıdır"

    config = _alertmanager_template()
    routes = config["route"]["routes"]
    first = routes[0]
    assert (
        first["receiver"] == "heartbeat"
    ), "Watchdog marşrutu siyahının ƏVVƏLİNDƏ olmalıdır (ilk uyğunluq qalib gəlir)"
    assert any(matcher.replace(" ", "") == 'alertname="Watchdog"' for matcher in first["matchers"])
    assert first["repeat_interval"] == "__WATCHDOG_REPEAT__"

    receivers = {receiver["name"]: receiver for receiver in config["receivers"]}
    heartbeat = receivers["heartbeat"]
    assert heartbeat.get("email_configs"), "heartbeat e-poçt göndərməlidir"
    assert not heartbeat.get("webhook_configs"), "heartbeat in-app webhook-a getməməlidir (daimi insident yaranar)"
    assert heartbeat["email_configs"][0].get("send_resolved") is False


def test_alertmanager_notification_failures_raise_a_critical_alert():
    rules = _rules()
    rule = rules.get("AlertmanagerNotificationsFailing")
    assert rule, "P1-3: AlertmanagerNotificationsFailing qaydası yoxdur"
    assert "alertmanager_notifications_failed_total" in rule["expr"]
    assert rule["labels"]["severity"] == "critical"
    # Alertmanager öz metriklərini verir — scrape job mövcud olmalıdır.
    prometheus = yaml.safe_load(PROMETHEUS_PATH.read_text(encoding="utf-8"))
    jobs = {job["job_name"]: job for job in prometheus["scrape_configs"]}
    assert "emsarena-alertmanager" in jobs


# ── P2-1 — Alertmanager → app webhook nginx üzərindən ─────────────────────


def test_alertmanager_webhook_goes_through_nginx_internal_location():
    config = _alertmanager_template()
    receivers = {receiver["name"]: receiver for receiver in config["receivers"]}
    webhooks = [hook for receiver in receivers.values() for hook in receiver.get("webhook_configs", [])]
    assert webhooks, "in-app webhook receiver-i yoxdur"
    for hook in webhooks:
        assert hook["url"] == f"http://nginx{WEBHOOK_PATH}", "P2-1: webhook birbaşa app:8000-ə getməməlidir"
        assert hook["http_config"]["authorization"]["type"] == "Bearer"

    block = _nginx_location_block(f"location = {WEBHOOK_PATH}")
    assert re.search(r"^\s*allow 172\.16\.0\.0/12;", block, flags=re.MULTILINE)
    assert re.search(r"^\s*deny all;", block, flags=re.MULTILINE)
    assert not re.search(r"^\s*allow 10\.0\.0\.0/8;", block, flags=re.MULTILINE), "webhook LAN-a açıq olmamalıdır"
    assert re.search(r"proxy_set_header\s+Host\s+localhost;", block)
    assert re.search(r"proxy_set_header\s+X-Forwarded-Proto\s+https;", block)
    assert "proxy_pass $emsarena_app;" in block
    assert "limit_req" not in block, "Alertmanager partiyası 429 almamalıdır (itən insident)"


@pytest.mark.django_db
@override_settings(
    SECURE_SSL_REDIRECT=True,
    ALLOWED_HOSTS=["10.0.2.42", "localhost", "127.0.0.1"],
    ALERTMANAGER_WEBHOOK_TOKEN="t0k",
)
def test_webhook_reachable_only_with_the_headers_nginx_sets():
    """Auditorun reproduksiyası: `.env.production.example` ALLOWED_HOSTS + SSL redirect."""
    client = Client()
    payload = json.dumps({"alerts": [], "status": "firing"})
    common = {"data": payload, "content_type": "application/json", "HTTP_AUTHORIZATION": "Bearer t0k"}

    # Əvvəlki konfiq: Alertmanager birbaşa app:8000-ə, XFP-siz POST edirdi.
    direct = client.post(WEBHOOK_PATH, HTTP_HOST="app:8000", **common)
    assert direct.status_code in (301, 400), f"birbaşa çağırış uğursuz olmalı idi: {direct.status_code}"

    # nginx daxili bloku: Host localhost + X-Forwarded-Proto https.
    via_nginx = client.post(WEBHOOK_PATH, HTTP_HOST="localhost", secure=True, **common)
    assert via_nginx.status_code == 200, via_nginx.content[:200]


# ── P2-2 — app scrape hər replikaya ayrıca ────────────────────────────────


def test_prometheus_scrapes_app_replicas_directly_via_compose_dns():
    prometheus = yaml.safe_load(PROMETHEUS_PATH.read_text(encoding="utf-8"))
    jobs = {job["job_name"]: job for job in prometheus["scrape_configs"]}
    app = jobs["emsarena-app"]
    assert "static_configs" not in app, "P2-2: tək nginx:80 hədəfi 8 replikanın sayğaclarını qarışdırır"
    dns = app["dns_sd_configs"][0]
    assert dns["names"] == ["app"] and dns["type"] == "A" and int(dns["port"]) == 8000
    # Django USE_X_FORWARDED_HOST=True + SECURE_PROXY_SSL_HEADER: ALLOWED_HOSTS
    # `localhost` və SSL-redirect-i keçmək üçün nginx `/metrics/` blokunun
    # başlıqları scrape-də təkrarlanır.
    headers = app["http_headers"]
    assert headers["X-Forwarded-Host"]["values"] == ["localhost"]
    assert headers["X-Forwarded-Proto"]["values"] == ["https"]
    assert app["metrics_path"] == "/metrics/"


@pytest.mark.django_db
@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    USE_X_FORWARDED_HOST=True,
    ALLOWED_HOSTS=["10.0.2.42", "localhost", "127.0.0.1"],
    METRICS_ALLOW_ANONYMOUS=True,
)
def test_direct_replica_scrape_with_prometheus_headers_is_not_redirected():
    """Prometheus `http_headers` ilə birbaşa `<replika-ip>:8000/metrics/` — 301/400 yox, 200."""
    client = Client()
    # Başlıqsız (əvvəlki vəziyyət): Host replika IP-sidir → DisallowedHost / SSL redirect.
    bare = client.get("/metrics/", HTTP_HOST="172.18.0.7:8000")
    assert bare.status_code in (301, 400)

    scraped = client.get(
        "/metrics/",
        HTTP_HOST="172.18.0.7:8000",
        HTTP_X_FORWARDED_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert scraped.status_code == 200, scraped.content[:200]
    assert scraped["Content-Type"].startswith("text/plain")


# ── P2-8 / P3-14 — Celery növbə qaydaları kollektorun verdiyi seriyalarla ──


def test_celery_queue_rules_match_collector_metric_labels():
    from apps.monitoring.collectors import MONITORED_QUEUES

    rules = _rules()
    assert "heavy" in MONITORED_QUEUES and "celery" in MONITORED_QUEUES
    assert rules["CeleryQueueBacklog"]["expr"].startswith('emsarena_celery_queue_length{queue="celery"}')
    assert rules["CeleryQueueBacklog"]["for"] == "2m", "P3-14: imtahan günü 60 s sweep-ləri üçün 10m gecdir"
    assert rules["CeleryHeavyQueueBacklog"]["expr"].startswith('emsarena_celery_queue_length{queue="heavy"}')
    heavy_down = rules["CeleryHeavyWorkerDown"]
    assert heavy_down["expr"].strip() == 'emsarena_celery_queue_workers{queue="heavy"} == 0'
    assert heavy_down["labels"]["severity"] == "critical"


# ── P3-7 — .trivyignore baxış tarixi keçməməlidir ─────────────────────────


def test_trivyignore_review_date_is_in_the_future_and_entries_are_justified():
    text = (ROOT / ".trivyignore").read_text(encoding="utf-8")
    dates = re.findall(r"Yenidən baxış: (\d{4}-\d{2}-\d{2})", text)
    assert dates, ".trivyignore-da «Yenidən baxış: YYYY-MM-DD» sətri yoxdur"
    latest = max(datetime.date.fromisoformat(value) for value in dates)
    assert (
        latest >= datetime.date.today()
    ), f"P3-7: .trivyignore baxış tarixi keçib ({latest}) — girişləri yenidən əsaslandırın"
    entries = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    assert entries, ".trivyignore boşdursa faylı silin"
    for entry in entries:
        assert re.fullmatch(r"(CVE-\d{4}-\d+|GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4})", entry), entry
    # Hər giriş şərhdə əsaslandırılmalıdır (fayl başlığı: «hər sətir ƏSASLANDIRILMALIDIR»).
    assert "vendor.txt" in text and "setuptools==70.3.0" in text


# ── P3-15 — advisory `safety` addımı silinib, pip-audit bloklayır ─────────


def test_security_workflow_has_no_advisory_safety_step_and_pip_audit_blocks():
    workflow = (ROOT / ".github/workflows/_security.yml").read_text(encoding="utf-8")
    assert not re.search(
        r"^\s*safety check", workflow, flags=re.MULTILINE
    ), "P3-15: `safety check … || true` yanıltıcı yaşıldır"
    assert "pip-audit -r requirements/base.txt" in workflow
    pip_audit_block = workflow.split("pip-audit -r requirements/base.txt", 1)[1][:300]
    assert "exit 1" in pip_audit_block


# ── 2026-09-14 infra auditi (wave 2): P3-8 / P3-9 şablon renderi ──────────

RENDER_SCRIPT = ROOT / "docker/render-template.sh"
BLACKBOX_TMPL_PATH = ROOT / "docker/blackbox/blackbox.tmpl.yml"
PROD_SMOKE_PATH = ROOT / ".github/workflows/_prod-smoke.yml"
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"


def _render(template: Path, tmp_path: Path, variables: dict[str, str]) -> str:
    if shutil.which("sh") is None:
        pytest.skip("sh yoxdur")
    output = tmp_path / (template.name + ".rendered")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **variables}
    result = subprocess.run(
        ["sh", str(RENDER_SCRIPT), str(template), str(output), *variables],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return output.read_text(encoding="utf-8")


_ALERTMANAGER_VARS = {
    "SMTP_HOST": "smtp-relay.brevo.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "user@example.com",
    "ALERT_FROM": "no-reply@emsarena.com",
    "ALERT_TO": "ops@example.com",
    "WATCHDOG_REPEAT": "6h",
}


@pytest.mark.parametrize(
    "secret",
    [
        "xsmtpsib-plain",
        'p|a&s/s\\w"o$rd',  # P3-8: `|` `&` `/` `\` `"` `$`
        "&&|||//\\\\",
    ],
)
def test_alertmanager_template_renders_valid_yaml_for_any_smtp_password(tmp_path, secret):
    rendered = _render(
        ALERTMANAGER_TMPL_PATH, tmp_path, {**_ALERTMANAGER_VARS, "SMTP_PASS": secret, "WEBHOOK_TOKEN": secret}
    )
    config = yaml.safe_load(rendered)
    assert config["global"]["smtp_auth_password"] == secret
    assert config["global"]["smtp_smarthost"] == "smtp-relay.brevo.com:587"
    assert config["route"]["routes"][0]["repeat_interval"] == "6h"
    receivers = {receiver["name"]: receiver for receiver in config["receivers"]}
    assert receivers["ops-all"]["webhook_configs"][0]["http_config"]["authorization"]["credentials"] == secret
    # Şablon başlığındakı izahlı `__PLACEHOLDER__` sözü istisna — real placeholder qalmamalıdır.
    assert set(re.findall(r"__[A-Z_]+__", rendered)) <= {"__PLACEHOLDER__"}


def test_legacy_sed_render_would_have_broken_on_pipe_and_ampersand(tmp_path):
    """Auditorun iddiasının sübutu: köhnə `sed -e "s|__X__|$X|g"` bu parolla pozulur."""
    if shutil.which("sed") is None:
        pytest.skip("sed yoxdur")
    secret = "p|a&s"
    legacy = subprocess.run(
        ["sed", "-e", f"s|__SMTP_PASS__|{secret}|g", str(ALERTMANAGER_TMPL_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    # `|` sed ayırıcısıdır → ya xəta, ya da parol kəsilir; `&` uyğun mətni qaytarır.
    assert legacy.returncode != 0 or f'smtp_auth_password: "{secret}"' not in legacy.stdout


def test_blackbox_probe_host_header_comes_from_healthcheck_host(tmp_path):
    template = BLACKBOX_TMPL_PATH.read_text(encoding="utf-8")
    assert 'Host: "10.0.2.42"' not in template, "P3-9: sabit host git-də qalmamalıdır"
    assert template.count('Host: "__HEALTHCHECK_HOST__"') == 2
    rendered = yaml.safe_load(_render(BLACKBOX_TMPL_PATH, tmp_path, {"HEALTHCHECK_HOST": "10.0.9.9"}))
    for module in ("http_2xx_lan", "http_login_lan"):
        assert rendered["modules"][module]["http"]["headers"]["Host"] == "10.0.9.9"

    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    blackbox = compose["services"]["blackbox_exporter"]
    assert blackbox["environment"]["HEALTHCHECK_HOST"] == "${HEALTHCHECK_HOST:-10.0.2.42}"
    command = " ".join(blackbox["command"])
    assert "render-template.sh" in command and " HEALTHCHECK_HOST " in command + " "
    assert "--config.file=/tmp/blackbox.yml" in command
    assert not (ROOT / "docker/blackbox/blackbox.yml").exists(), "köhnə statik fayl silinməlidir (mount şablona baxır)"


def test_render_script_rejects_unsafe_variable_names_and_leaves_other_lines_untouched(tmp_path):
    template = tmp_path / "t.yml"
    template.write_text('a: "__PW__"\nb: keep \\ literal & | stuff\n', encoding="utf-8")
    rendered = _render(template, tmp_path, {"PW": "x"})
    assert rendered == 'a: "x"\nb: keep \\ literal & | stuff\n'
    bad = subprocess.run(
        ["sh", str(RENDER_SCRIPT), str(template), str(tmp_path / "o.yml"), "x;y"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2 and "invalid variable name" in bad.stderr


# ── prod-smoke: webhook yolu nginx üzərindən (P2-1 qalığı) ────────────────


def test_prod_smoke_posts_to_the_webhook_through_nginx_and_checks_redis_argv():
    workflow = PROD_SMOKE_PATH.read_text(encoding="utf-8")
    steps = {step["name"]: step for step in yaml.safe_load(workflow)["jobs"]["prod-smoke"]["steps"]}
    start = next(step for name, step in steps.items() if "Start production stack" in name)
    assert start["env"]["ALERTMANAGER_WEBHOOK_TOKEN"], "token həm app-a, həm Alertmanager-ə getməlidir"

    webhook = next(step for name, step in steps.items() if "Alertmanager webhook" in name)
    run = webhook["run"]
    assert f"WEBHOOK_PATH={WEBHOOK_PATH}" in run
    assert "-H 'Host: localhost' -H 'X-Forwarded-Proto: https'" in run, "nginx daxili blokunun başlıqları"
    assert '"$NO_TOKEN" != "403"' in run and '"$WITH_TOKEN" != "200"' in run
    assert "exec -T alertmanager wget" in run and "--post-data" in run
    assert "/tmp/alertmanager.yml" in run
    assert webhook["env"]["ALERTMANAGER_WEBHOOK_TOKEN"] == start["env"]["ALERTMANAGER_WEBHOOK_TOKEN"]

    redis_step = next(step for name, step in steps.items() if "Redis password" in name)
    assert "/proc/1/cmdline" in redis_step["run"] and "requirepass" in redis_step["run"]


# ── W7 `w7cohort` (2026-09-14) infra P3 — nginx nosniff + /health/ daxili ──


def _nginx_conf() -> str:
    return NGINX_CONF_PATH.read_text(encoding="utf-8")


def test_nginx_direct_file_locations_send_nosniff_always():
    """Birbaşa nginx-dən verilən fayllar Django SecurityMiddleware-dən keçmir —
    `X-Content-Type-Options: nosniff` (`always`) hər belə blokda açıq yazılmalıdır.
    `add_header` blokda olanda yuxarıdan miras gəlmir, ona görə hər biri ayrı yoxlanır."""
    for prefix in (
        "location /static/",
        "location /media/post_images/",
        "location /media/course_covers/",
        "location /internal_media/",
    ):
        block = _nginx_location_block(prefix)
        assert "add_header X-Content-Type-Options nosniff always;" in block, prefix
        # Mövcud Cache-Control başlığı itməməlidir (eyni blokda yan-yana).
        assert "add_header Cache-Control" in block, prefix


def test_nginx_proxied_media_block_does_not_duplicate_django_nosniff():
    """Proxied /media/ cavabı Django-dan keçir — nosniff-i Django qoyur; nginx-də
    təkrar `add_header` iki eyni başlıq yaradardı."""
    block = _nginx_location_block("location /media/ {")
    assert "proxy_pass" in block
    assert "X-Content-Type-Options" not in block.replace("# nosniff burada ƏLAVƏ EDİLMİR", "")


def test_nginx_health_is_internal_only_and_ping_stays_public():
    """/health/ `build.sha` + komponent statusları publik olmamalıdır; allow siyahısı
    `/metrics/` ilə eynidir (loopback + docker bridge + LAN monitorinq). /ping/ isə
    app healthcheck və deploy-un ilk qapısıdır — ayrıca bloku YOXDUR, `location /`
    ilə publik qalır."""
    conf = _nginx_conf()
    health = _nginx_location_block("location = /health/")
    metrics = _nginx_location_block("location /metrics/")
    allow_re = re.compile(r"^\s*(allow|deny)\s+[^;]+;", flags=re.MULTILINE)
    assert [m.group(0).strip() for m in allow_re.finditer(health)] == [
        m.group(0).strip() for m in allow_re.finditer(metrics)
    ], "/health/ allow/deny siyahısı /metrics/ ilə eyni olmalıdır"
    assert "deny all;" in health
    assert "allow 172.16.0.0/12;" in health, "docker bridge (deploy host curl-u, blackbox probe)"
    assert "allow 127.0.0.1;" in health
    # Deploy qapısı `Host: $HEALTHCHECK_HOST` + https ilə gəlir — başlıqlar `location /` kimi.
    assert "proxy_set_header Host              $host;" in health
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in health
    assert "proxy_set_header X-Forwarded-For   $remote_addr;" in health
    assert "location = /ping/" not in conf and "location /ping/" not in conf


def test_deploy_and_smoke_health_probes_come_from_allowed_sources():
    """remote_deploy.sh loopback-dan (`https://127.0.0.1` → bridge gateway), CI
    prod-smoke `http://localhost` → eyni; blackbox `https://nginx/health/` konteynerdən.
    Hamısı 172.16.0.0/12 / loopback allow-una düşür — /ping/ isə ilk qapı olaraq qalır."""
    deploy = (ROOT / "scripts/deploy/remote_deploy.sh").read_text(encoding="utf-8")
    assert 'APP_BASE_URL="https://127.0.0.1"' in deploy
    assert 'PING_PATH="${PING_PATH:-/ping/}"' in deploy and 'HEALTH_PATH="${HEALTH_PATH:-/health/}"' in deploy
    smoke = PROD_SMOKE_PATH.read_text(encoding="utf-8")
    assert "http://localhost/health/" in smoke and "http://localhost/ping/" in smoke
    prometheus = yaml.safe_load(PROMETHEUS_PATH.read_text(encoding="utf-8"))
    blackbox = next(job for job in prometheus["scrape_configs"] if job["job_name"] == "emsarena-blackbox")
    targets = blackbox["static_configs"][0]["targets"]
    assert "https://nginx/health/" in targets and "https://nginx/ping/" in targets
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    subnet = compose["networks"]["emsarena-network"]["ipam"]["config"][0]["subnet"]
    assert subnet.endswith("172.18.0.0/16}") or subnet == "172.18.0.0/16", subnet
