"""
Image build-info oxuyucusu — /health/ üçün (P1-07, Codex audit 2026-09-13).

docker/build-info.sh image qurulanda ``/app/build-info.json`` yazır (git SHA,
Django/Python versiyası, qurulma vaxtı). Bu modul həmin faylı BİR DƏFƏ oxuyub
prosesin ömrü boyu keşləyir və /health/ cavabına ``build`` açarı kimi əlavə
edir ki, işləyən image mənbədən geri qalanda (image drift) sahib bunu
görsün. Yalnız oxumadır; sirr yoxdur. Fayl yoxdursa (lokal dev, köhnə image)
``{"sha": "unknown"}`` qaytarılır — health endpoint heç vaxt bu səbəbdən
sınmır.

Yol: ``EMS_BUILD_INFO_PATH`` env (test/override) → ``BASE_DIR/build-info.json``
(image-də ``/app/build-info.json``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# /health/ çıxışında yalnız bu açarlar keçir — faylda başqa nə olsa da sızmır.
_EXPOSED_KEYS = ("sha", "django", "python", "built_at")
_UNKNOWN_BUILD: dict = {"sha": "unknown"}

_LOCK = threading.Lock()
_CACHE: dict = {"loaded": False, "value": None}


def build_info_path() -> Path:
    override = os.getenv("EMS_BUILD_INFO_PATH", "").strip()
    if override:
        return Path(override)
    return Path(settings.BASE_DIR) / "build-info.json"


def _read_build_info() -> dict:
    path = build_info_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(_UNKNOWN_BUILD)
    except (OSError, ValueError):
        # Zədəli/oxunmaz fayl health-i sındırmamalıdır — «unknown» + log.
        logger.warning("build-info oxunmadı: %s", path, exc_info=True)
        return dict(_UNKNOWN_BUILD)

    if not isinstance(raw, dict):
        return dict(_UNKNOWN_BUILD)

    info = {key: str(raw[key]) for key in _EXPOSED_KEYS if raw.get(key) not in (None, "")}
    info.setdefault("sha", "unknown")
    return info


def get_build_info() -> dict:
    """Keşlənmiş build-info (dict surəti) — fayl prosesin ömründə dəyişmir."""
    if _CACHE["loaded"]:
        return dict(_CACHE["value"])
    with _LOCK:
        if not _CACHE["loaded"]:
            _CACHE["value"] = _read_build_info()
            _CACHE["loaded"] = True
    return dict(_CACHE["value"])


def reset_build_info_cache() -> None:
    """Testlər üçün: növbəti çağırışda fayl yenidən oxunsun."""
    with _LOCK:
        _CACHE["loaded"] = False
        _CACHE["value"] = None
