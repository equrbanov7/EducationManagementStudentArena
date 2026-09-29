"""Deploy-dan SONRA canlı imtahanın prod smoke yoxlaması (YALNIZ-OXU).

`manage.py shell`-ə STDIN ilə ötürülür (prod-exam-ops.yml). Heç nə yazmır:
* anonim PIN giriş səhifəsi (`/live/`) render olunur (şablon/JS i18n/kontekst xətası yoxdur);
* ES modul fayllarının VERSİYASIZ nüsxələri STATIC_ROOT-dadır — brauzer `import './audio.js?v=…'` ilə
  məhz onları istəyir (manifest storage modul importlarını hash-ləmir, nginx onları birbaşa verir);
* entry skriptlərin hash-li adları manifestdə var.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.test import Client

hosts = [h.lstrip(".") for h in (settings.ALLOWED_HOSTS or ["localhost"]) if h and h != "*"][:4]
for host in hosts:
    # nginx arxasında HTTPS X-Forwarded-Proto ilə tanınır (SECURE_PROXY_SSL_HEADER) — başlıqsız 301 gəlir.
    client = Client(secure=True, HTTP_HOST=host, REMOTE_ADDR="10.0.2.10", HTTP_X_FORWARDED_PROTO="https")
    response = client.get("/live/")
    location = response.headers.get("Location", "")
    body = response.content.decode("utf-8", "ignore") if response.status_code == 200 else ""
    has_form = "pin" in body.lower() and "<form" in body.lower()
    print(f"GET /live/ host={host} -> {response.status_code} {location} pin_form={has_form} bytes={len(body)}")

root = Path(settings.STATIC_ROOT)
missing = []
for graph in ("host_lobby", "player"):
    folder = root / "js" / graph
    count = len(list(folder.glob("*.js"))) if folder.is_dir() else 0
    print(f"static js/{graph}: {count} files")
for rel in (
    "js/host_lobby/stage.js",
    "js/host_lobby/audio.js",
    "js/host_lobby/stage_logic.js",
    "js/player/finale.js",
    "js/player/config.js",
    "css/stage/_part1.css",
):
    if not (root / rel).is_file():
        missing.append(rel)
print(f"missing_unhashed: {missing or 'none'}")
for entry in ("js/host_lobby/host_lobby.entry.js", "js/player/player.entry.js"):
    if not hasattr(staticfiles_storage, "stored_name"):
        print(f"manifest {entry} -> (manifest storage deyil — lokal)")
        continue
    try:
        print(f"manifest {entry} -> {staticfiles_storage.stored_name(entry)}")
    except ValueError as exc:
        print(f"manifest {entry} -> MISSING ({exc})")
