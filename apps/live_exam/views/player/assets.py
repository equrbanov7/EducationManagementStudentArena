"""LXNET (2026-10-02): oyunçu ekranının statik faylları — YEGANƏ mənbə.

* Oyun ekranı (``player_screen.html``) CSS/skriptləri buradan çəkir və BÜTÜN ES modullarına
  ``<link rel="modulepreload">`` verir: brauzer import qrafını 4–5 dalğa (hər biri bir RTT)
  əvəzinə bir dalğada yükləyir.
* Gözləmə otağı (``wait_room.html``) eyni URL-ləri ``<link rel="prefetch">`` ilə lobbi vaxtı
  (adətən dəqiqələrlə boş) əvvəlcədən keşə alır → «Oyun başlayır!» anında zəif şəbəkəli telefon
  oyun ekranını keşdən açır, 1-ci sual vaxtında görünür.

Modul URL-ləri nisbi importların brauzerdə HƏLL OLUNDUĞU formadadır (``STATIC_URL`` + hash-siz ad +
``?v=`` tokeni) — fərqli URL eyni faylı ikinci dəfə yükləyərdi (test_static_module_versions.py).
Sual məzmunu burada YOXDUR — yalnız kod/üslub faylları (sızma riski yoxdur).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

PLAYER_JS_DIR = Path(__file__).resolve().parents[2] / "static" / "js" / "player"
ENTRY_MODULE = "player.entry.js"
ENTRY_VERSION = "lxp-20261019s"
#: ``./x.js`` və ortaq SAF modullar ``../host_lobby/x.js`` (stage_logic.js, code_text.js — 2026-10-19).
_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(['"])(\./|\.\./host_lobby/)([\w.-]+\.js)(\?v=[\w.-]+)?\1"""
)

#: (yol, versiya) — player_screen.html-in stil faylları (sıra vacibdir).
PLAYER_CSS = (
    ("css/design-tokens.css", "20260701-1"),
    ("css/live_avatar.css", "lx-20260929"),
    ("css/live_theme.css", "lx-20260929"),
    ("css/player/_base.css", "lxp-20260930"),
    ("css/player/_ui.css", "lxp-20261002"),
    ("css/player/_round.css", "lxp-20261019"),
    ("css/player/_answer.css", "lxp-20261019m4"),
    ("css/player/_reveal.css", "lxp-20260930"),
    ("css/player/_finale.css", "lxp-20260929"),
    ("css/live_code_text.css", "lx-20261019"),
    # 2026-10-19: «Rəsmi» təqdimat üslubu qatı (body[data-lx-style="formal"]) — SONDA, üstələyir.
    ("css/live_formal/_base.css", "lx-20261019s"),
    ("css/live_formal/_player.css", "lx-20261019s"),
)
#: Modul yüklənməzdən ƏVVƏL işləyən klassik skriptlər (player_screen.html sırası ilə).
PLAYER_CLASSIC_JS = (
    ("js/ems_ajax_init.js", ""),
    ("js/player_screen_config.js", "lxp-20260929"),
    ("js/live_avatar_catalog.js", "lx-20260929"),
    ("js/live_avatar_renderer.js", "lx-20261019s"),
)


def _versioned(path: str, version: str) -> str:
    url = static(path)
    return f"{url}?v={version}" if version else url


@lru_cache(maxsize=1)
def player_module_urls() -> tuple[str, ...]:
    """Giriş modulundan əlçatan BÜTÜN nisbi importlar (rekursiv), brauzerin həll etdiyi URL ilə."""
    static_js = settings.STATIC_URL.rstrip("/") + "/js/"
    seen: dict[str, str] = {}
    stack = [("player", ENTRY_MODULE)]
    while stack:
        folder, name = stack.pop()
        try:
            source = (PLAYER_JS_DIR.parent / folder / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _IMPORT_RE.finditer(source):
            child_folder = folder if match.group(2) == "./" else "host_lobby"
            child, version = match.group(3), match.group(4) or ""
            key = f"{child_folder}/{child}"
            if key not in seen:
                seen[key] = f"{static_js}{key}{version}"
                stack.append((child_folder, child))
    return tuple(seen[key] for key in sorted(seen))


def player_assets() -> dict[str, object]:
    """Şablon konteksti: ``css``, ``classic_js``, ``entry``, ``modules``."""
    return {
        "css": [_versioned(path, version) for path, version in PLAYER_CSS],
        "classic_js": [_versioned(path, version) for path, version in PLAYER_CLASSIC_JS],
        "entry": _versioned(f"js/player/{ENTRY_MODULE}", ENTRY_VERSION),
        "modules": list(player_module_urls()),
    }
