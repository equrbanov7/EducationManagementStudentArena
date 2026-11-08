"""nginx texniki xidmət səhifəsi (2026-11-06).

Sahib: «502 yazmasın, yerinə düzəliş gedir kimi görünsün». Deploy app replikalarını eyni anda
yenidən başladanda nginx xam «502 Bad Gateway» əvəzinə öz statik səhifəsini verir. Səhifə
Django-dan asılı olmamalıdır (ayrıca mount olunan qovluq), status kodu dəyişməməlidir və
CSP 'unsafe-inline' vermədiyi üçün stil/skript yalnız xarici fayldır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NGINX = ROOT / "docker/nginx/nginx.conf"
MAINT_DIR = ROOT / "docker/nginx/maintenance"


def _conf() -> str:
    return NGINX.read_text(encoding="utf-8")


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


def test_upstream_errors_keep_their_status_and_go_to_the_maintenance_page():
    conf = _conf()
    server = conf[: conf.index("listen 8081;")]
    # `=` yoxdur → 502/503/504 status kodu saxlanır (200-ə çevrilmir).
    assert "    error_page 502 503 504 $ems_maintenance_uri;\n" in server
    assert not re.search(r"error_page 502 503 504 =", conf)
    # Django-nun öz 5xx cavabları tutulmur.
    assert "proxy_intercept_errors on" not in conf
    # `location /` öz error_page-i (418) olduğu üçün miras almır — sətir orada da olmalıdır.
    root = _block(conf, "    location / {\n        # Kənar zonadan")
    assert "error_page 502 503 504 $ems_maintenance_uri;" in root


def test_maintenance_locations_are_served_by_nginx_without_django():
    conf = _conf()
    for name in ("index.html", "maintenance.json"):
        block = _block(conf, f"location = /_ems_maintenance/{name} {{")
        assert "internal;" in block
        assert f"alias /var/www/maintenance/{name};" in block
        assert 'add_header Cache-Control "no-store" always;' in block
        assert "add_header Retry-After 15 always;" in block
        assert "proxy_pass" not in block
    for name in ("maintenance.css", "maintenance.js"):
        block = _block(conf, f"location = /_ems_maintenance/{name} {{")
        assert "internal;" not in block  # brauzer ayrıca istəyir
        assert f"alias /var/www/maintenance/{name};" in block
        assert "proxy_pass" not in block
    html_block = _block(conf, "location = /_ems_maintenance/index.html {")
    assert "style-src 'self'; script-src 'self'" in html_block


def test_xhr_and_json_requests_get_the_json_body():
    conf = _conf()
    assert re.search(r'"~\^1:"\s+/_ems_maintenance/maintenance\.json;', conf)
    assert re.search(r'"~\*application/json"\s+/_ems_maintenance/maintenance\.json;', conf)
    body = json.loads((MAINT_DIR / "maintenance.json").read_text(encoding="utf-8"))
    assert body["ok"] is False and body["error"] == "maintenance"


def test_maintenance_dir_is_mounted_into_the_nginx_container():
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert "./docker/nginx/maintenance:/var/www/maintenance:ro" in compose["services"]["nginx"]["volumes"]


def test_maintenance_page_has_no_inline_assets_and_is_in_azerbaijani():
    html = (MAINT_DIR / "index.html").read_text(encoding="utf-8")
    assert '<html lang="az">' in html
    assert "Sistemdə yeniləmə gedir" in html
    assert "Qərbi Kaspi Universiteti" in html
    assert 'href="/_ems_maintenance/maintenance.css"' in html
    assert 'src="/_ems_maintenance/maintenance.js"' in html
    assert "<style" not in html
    assert "style=" not in html
    assert not re.search(r"\son[a-z]+\s*=", html)
    for match in re.finditer(r"<script\b([^>]*)>", html):
        assert "src=" in match.group(1)
    assert "prefers-color-scheme: dark" in (MAINT_DIR / "maintenance.css").read_text(encoding="utf-8")
