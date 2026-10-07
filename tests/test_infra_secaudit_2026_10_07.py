"""Təhlükəsizlik auditi 2026-10-07 — deploy konfiqurasiyası (CI, nginx, compose, settings).

DB-siz statik qapılar: düzəlişlər geri sürüşməsin. Hər test bir tapıntıya bağlıdır
(hesabat: agent cavabı / commit mesajları `sec(...)`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(_read(path))


def _triggers(doc: dict) -> dict:
    # PyYAML `on:` açarını bool True kimi oxuyur.
    on = doc.get(True, doc.get("on"))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return on or {}


def _jobs(doc: dict) -> dict:
    return doc.get("jobs") or {}


def _steps(job: dict) -> list[dict]:
    return job.get("steps") or []


def _is_self_hosted(job: dict) -> bool:
    runs_on = job.get("runs-on")
    labels = runs_on if isinstance(runs_on, list) else [runs_on]
    return "self-hosted" in labels


# ── CI-1: workflow injection — girişlər `run:`-a birbaşa düşmür ─────────────

_UNTRUSTED_EXPR = re.compile(r"\$\{\{\s*(inputs\.|github\.event\.|github\.head_ref)", re.IGNORECASE)


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_run_scripts_never_interpolate_inputs_or_event_payload(path):
    for job_name, job in _jobs(_load(path)).items():
        for step in _steps(job):
            script = step.get("run") or ""
            hits = _UNTRUSTED_EXPR.findall(script)
            assert not hits, f"{path.name}:{job_name}:{step.get('name')!r} — girişi env: ilə ötürün"


def test_seed_database_validates_inputs_and_keeps_plain_dump_private():
    text = _read(WORKFLOWS / "seed-database.yml")
    assert "ASSET_ID: ${{ github.event.inputs.asset_id }}" in text
    assert "case \"$ASSET_ID\" in (*[!0-9]*|'')" in text
    assert "case \"$EXPECTED_USERS_INPUT\" in (*[!0-9]*|'')" in text
    download = text[text.index("Download + decrypt dump") :]
    assert download.index("umask 077") < download.index("openssl enc -d")


# ── CI-2: least-privilege GITHUB_TOKEN ─────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [p for p in _workflow_files() if set(_triggers(_load(p))) != {"workflow_call"}],
    ids=lambda p: p.name,
)
def test_every_entry_workflow_declares_top_level_permissions(path):
    doc = _load(path)
    assert "permissions" in doc, f"{path.name}: top-level `permissions:` yoxdur → repo defoltu (yazma) token"
    perms = doc["permissions"]
    assert perms == {} or perms == {"contents": "read"}, f"{path.name}: top-level defolt yalnız oxuma olmalıdır"


# ── CI-3: self-hosted (prod server) runner-in ifşası ───────────────────────


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_self_hosted_jobs_are_production_gated_and_unreachable_from_pull_requests(path):
    doc = _load(path)
    triggers = set(_triggers(doc))
    assert not triggers & {"pull_request_target", "workflow_run"}, f"{path.name}: imtiyazlı trigger"
    for job_name, job in _jobs(doc).items():
        if not _is_self_hosted(job):
            continue
        assert job.get("environment") == "production", f"{path.name}:{job_name}"
        if "pull_request" in triggers:
            condition = str(job.get("if", ""))
            assert "github.event_name == 'push'" in condition, f"{path.name}:{job_name} PR-dan işə düşə bilər"


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_self_hosted_checkouts_do_not_persist_the_token_on_the_server(path):
    for job_name, job in _jobs(_load(path)).items():
        if not _is_self_hosted(job):
            continue
        for step in _steps(job):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert (step.get("with") or {}).get("persist-credentials") is False, f"{path.name}:{job_name}"


# ── CI-4: təchizat zənciri — action-lar SHA ilə, gitleaks checksum ilə ──────

_USES = re.compile(r"^\s*(?:- )?uses:\s*(\S+)(.*)$", re.MULTILINE)


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_actions_are_pinned_to_full_commit_shas_with_version_comment(path):
    for ref, rest in _USES.findall(_read(path)):
        if ref.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{path.name}: {ref} SHA ilə pin-lənməyib"
        assert re.match(r"\s+# v\d", rest), f"{path.name}: {ref} — Dependabot üçün `# vX` şərhi lazımdır"


def test_gitleaks_tarball_is_verified_before_install():
    text = _read(WORKFLOWS / "_secret-scan.yml")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "| tar" not in code, "curl | tar — yoxlamasız binar"
    assert re.search(r'GITLEAKS_SHA256="[0-9a-f]{64}"', text)
    assert text.index("sha256sum -c -") < text.index("tar -xzf")


def test_pip_audit_covers_the_hash_locked_sets_that_are_actually_installed():
    text = _read(WORKFLOWS / "_security.yml")
    assert "for lock in requirements/production.lock requirements/test.lock; do" in text
    assert re.search(r'pip install "pip-audit==\d+\.\d+\.\d+"', text)


# ── CI-5: artefaktlar və prod hostdakı müvəqqəti fayllar ────────────────────


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_every_artifact_upload_has_a_bounded_retention(path):
    for job_name, job in _jobs(_load(path)).items():
        for step in _steps(job):
            if str(step.get("uses", "")).startswith("actions/upload-artifact@"):
                retention = (step.get("with") or {}).get("retention-days")
                assert retention is not None, f"{path.name}:{job_name}: retention-days yoxdur (defolt 90 gün)"
                assert int(retention) <= 30, f"{path.name}:{job_name}"


def test_load_test_keeps_its_venv_and_report_in_the_job_private_runner_temp():
    text = _read(WORKFLOWS / "load-test.yml")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "/tmp/load" not in code
    assert 'python3 -m venv "$RUNNER_TEMP/loadenv"' in code
    assert "path: ${{ runner.temp }}/loadreport/" in code
    assert re.search(r"retention-days: 7\b", code)


def test_exam_ops_does_not_use_the_bash_groups_builtin_for_an_input():
    doc = _load(WORKFLOWS / "prod-exam-ops.yml")
    env = _jobs(doc)["run-script"]["env"]
    assert "GROUPS" not in env, "bash GROUPS massividir — mühit dəyəri əzilir"
    assert env["GROUPS_INPUT"] == "${{ inputs.groups }}"


# ── NGX-1: proxy başlıqlarına etibar (AD-10) və nginx-in özü verdiyi cavablar ────

NGINX = ROOT / "docker/nginx/nginx.conf"


def _location_blocks(conf: str) -> dict[str, str]:
    """Əsas (80/443) server blokunun location-ları — :8081 stub_status server-i daxil deyil."""
    conf = conf[: conf.index("listen 8081;")]
    blocks = {}
    for match in re.finditer(r"^    location ([^{]+)\{", conf, flags=re.MULTILINE):
        depth = 0
        for index in range(match.end() - 1, len(conf)):
            if conf[index] == "{":
                depth += 1
            elif conf[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks[match.group(1).strip()] = conf[match.start() : index + 1]
                    break
    return blocks


def test_every_proxied_location_overwrites_x_forwarded_host_and_port():
    """Django USE_X_FORWARDED_HOST/PORT=True — müştərinin göndərdiyi dəyər app-a çatmamalıdır."""
    proxied = {name: body for name, body in _location_blocks(_read(NGINX)).items() if "proxy_pass" in body}
    assert len(proxied) >= 8
    for name, body in proxied.items():
        if "proxy_set_header Host              localhost;" in body:
            assert "proxy_set_header X-Forwarded-Host  localhost;" in body, name
        else:
            assert "proxy_set_header Host              $host;" in body, name
            assert "proxy_set_header X-Forwarded-Host  $host;" in body, name
            assert "proxy_set_header X-Forwarded-Port  $server_port;" in body, name


def test_tls_session_tickets_are_off_and_protocols_stay_modern():
    conf = _read(NGINX)
    assert "ssl_session_tickets off;" in conf
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in conf
    assert "server_tokens off;" in conf


def test_public_media_served_by_nginx_has_a_sandbox_csp_and_protected_media_is_rate_limited():
    blocks = _location_blocks(_read(NGINX))
    csp = "add_header Content-Security-Policy \"default-src 'none'; frame-ancestors 'self'; sandbox\" always;"
    for prefix in ("/media/post_images/", "/media/course_covers/"):
        assert "add_header X-Content-Type-Options nosniff always;" in blocks[prefix]
        assert csp in blocks[prefix]
    assert "limit_req zone=emsarena_general burst=1000 nodelay;" in blocks["/media/"]


def test_metrics_health_and_webhook_stay_bridge_and_loopback_only():
    blocks = _location_blocks(_read(NGINX))
    for name in ("/metrics/", "= /health/", "= /api/superadmin/monitoring/alertmanager-webhook/"):
        body = blocks[name]
        assert re.findall(r"allow\s+(\S+);", body) == ["127.0.0.1", "172.16.0.0/12"], name
        assert "deny all;" in body, name


# ── CMP-1: compose — publik portlar, sərtləşdirmə, Prometheus lifecycle ─────────

COMPOSE = ROOT / "docker-compose.prod.yml"
_PRIVILEGED_OK = {"cadvisor", "piston"}
_CAP_DROP_REQUIRED = {
    "arp-agent",
    "postgres_exporter",
    "node_exporter",
    "alertmanager",
    "prometheus",
    "grafana",
    "redis_exporter",
    "nginx_exporter",
    "pgbouncer_exporter",
    "blackbox_exporter",
    "loki",
    "docker-socket-proxy",
}


def _services() -> dict:
    return _load(COMPOSE)["services"]


def test_only_nginx_publishes_public_ports_and_only_on_ipv4():
    for name, svc in _services().items():
        for port in svc.get("ports", []):
            spec = str(port)
            if name == "nginx":
                assert spec in {"0.0.0.0:80:80", "0.0.0.0:443:443"}, spec
            else:
                assert spec.startswith("127.0.0.1:"), f"{name}: {spec} loopback-a bağlı deyil"


def test_host_namespaces_and_privileged_mode_are_limited_to_the_justified_services():
    for name, svc in _services().items():
        if svc.get("network_mode") == "host":
            assert name in {"arp-agent", "node_exporter"}, name
        if svc.get("pid") == "host":
            assert name == "node_exporter", name
        if svc.get("privileged"):
            assert name in _PRIVILEGED_OK, name


@pytest.mark.parametrize("name", sorted(set(_load(COMPOSE)["services"]) - _PRIVILEGED_OK))
def test_non_privileged_services_cannot_gain_privileges(name):
    svc = _services()[name]
    assert "no-new-privileges:true" in svc.get("security_opt", []), name
    if name in _CAP_DROP_REQUIRED:
        assert svc.get("cap_drop") == ["ALL"], name


def test_arp_agent_runs_unprivileged_with_a_read_only_rootfs():
    svc = _services()["arp-agent"]
    assert svc["user"] == "65534:65534"
    assert svc["read_only"] is True


def test_prometheus_lifecycle_api_is_disabled_and_deploy_reloads_with_sighup():
    assert "--web.enable-lifecycle" not in _services()["prometheus"]["command"]
    deploy = _read(ROOT / "scripts/deploy/remote_deploy.sh")
    assert "exec -T prometheus kill -HUP 1" in deploy
    assert "/-/reload" not in deploy


# ── DJ-1: Django — dil kukisi ─────────────────────────────────────────────────────


def test_language_cookie_follows_session_cookie_secure_in_production():
    assert "LANGUAGE_COOKIE_SECURE = SESSION_COOKIE_SECURE" in _read(ROOT / "config/settings/production.py")
