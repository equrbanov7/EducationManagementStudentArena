"""FCM kredensialı və push açarı — push-un «işləyirmi» sualının TƏK cavab yeri.

``FCM_SERVICE_ACCOUNT_JSON`` üç formada qəbul olunur (deploy-a uyğun olanı seçilir):

* fayl yolu (``/run/secrets/fcm.json``) — konteynerə mount edilmiş fayl;
* base64 (``ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIs…``) — ``.env``-də tək sətir (prod workflow bunu yazır);
* xam JSON (``{"type": "service_account", …}``) — lokal sınaq.

Kredensial yoxdur / yararsızdırsa push NO-OP-dur: bildirişlər yaranır, telefona göndərilmir (loqda yalnız say).
Açarın özü heç vaxt loqa yazılmır.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)

_REQUIRED = ("client_email", "private_key", "token_uri")


@dataclass(frozen=True)
class Credentials:
    project_id: str
    client_email: str
    private_key: str
    token_uri: str


def _parse(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        text = raw
    elif os.path.isfile(raw):
        with open(raw, encoding="utf-8") as handle:
            text = handle.read()
    else:
        try:
            text = base64.b64decode(raw, validate=False).decode("utf-8")
        except ValueError:  # binascii.Error + UnicodeDecodeError
            return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=4)
def _load(raw: str, project_id: str) -> Credentials | None:
    try:
        data = _parse(raw)
    except OSError:
        data = None
    if not data or any(not data.get(key) for key in _REQUIRED):
        if raw:
            logger.warning("Push: FCM_SERVICE_ACCOUNT_JSON oxunmadı və ya natamamdır — push söndürülüb.")
        return None
    project = project_id or str(data.get("project_id") or "")
    if not project:
        logger.warning("Push: FCM layihə id-si yoxdur (FCM_PROJECT_ID / project_id) — push söndürülüb.")
        return None
    return Credentials(
        project_id=project,
        client_email=str(data["client_email"]),
        private_key=str(data["private_key"]),
        token_uri=str(data["token_uri"]),
    )


def credentials() -> Credentials | None:
    """Etibarlı FCM kredensialı və ya ``None`` (proses daxilində keşlənir — ``settings`` dəyişsə açar da dəyişir)."""
    return _load(
        str(getattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "") or ""),
        str(getattr(settings, "FCM_PROJECT_ID", "") or "").strip(),
    )


def is_configured() -> bool:
    return credentials() is not None


def push_enabled() -> bool:
    """Push göndərilsinmi: kredensial var VƏ «Sistem tənzimləmələri» açarı yandırılıb."""
    if not is_configured():
        return False
    from core.runtime_settings_push import push_enabled_setting

    return push_enabled_setting()


def chunk_size() -> int:
    try:
        return max(1, int(getattr(settings, "PUSH_SEND_CHUNK", 100)))
    except (TypeError, ValueError):
        return 100


__all__ = ["Credentials", "chunk_size", "credentials", "is_configured", "push_enabled"]
