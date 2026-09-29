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

host = (settings.ALLOWED_HOSTS or ["localhost"])[0].lstrip(".")
response = Client(secure=True, HTTP_HOST=host).get("/live/")
print(f"GET /live/ -> {response.status_code}")

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
