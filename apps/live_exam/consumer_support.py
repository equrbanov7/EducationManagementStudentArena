"""
Canlı viktorina WebSocket consumer-ləri üçün köməkçilər (Audit 2026-09-28 LX-BE).

* **Ucuz ön-autentifikasiya** — oyunçu token-inin İMZASI (DB-siz) və ya daxil olmuş
  istifadəçi yoxdursa socket DB-yə/limit sayğacına toxunmadan bağlanır (4401).
  Real və uydurma PIN üçün cavab EYNİDİR → PIN «oracle»-u və anonim ad siyahısı
  (LXS-15) bağlanır.
* **Qoşulma limitləri** — (a) kimlik (oyunçu client_id / istifadəçi) üzrə adi limit;
  (b) (PIN, İP) üzrə GENİŞ tavan: bir NAT arxasındakı 150 tələbəlik sinif zəif
  Wi-Fi-da yenidən qoşulanda bloklanmır, amma bir İP-dən sonsuz qoşulma da olmur.
* **Mesaj qoruyucuları** — ölçü həddi, binar kadrlar, yararsız JSON.
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.live_exam.auth import LIVE_CLIENT_ID_COOKIE_NAME, PLAYER_COOKIE_NAME, load_player_token_payload
from apps.live_exam.constants import SERVER_AUTO_REVEAL_GRACE_SECONDS
from core.asgi_scope import scope_client_ip

#: Bir klient mesajının maksimal ölçüsü (simvol). Həqiqi cavab mesajı < 300 simvoldur.
WS_MAX_MESSAGE_CHARS = 4096
#: WebSocket bağlanma kodları.
CLOSE_UNAUTHORIZED = 4401
CLOSE_KICKED = 4403
CLOSE_RATE_LIMITED = 4429
CLOSE_MESSAGE_TOO_BIG = 1009

WS_CONNECT_SCOPE = "live_exam.ws.connect"
WS_CONNECT_IP_SCOPE = "live_exam.ws.connect.ip"
WS_MSG_SCOPE = "live_exam.ws.message"
WS_ANSWER_SCOPE = "live_exam.ws.answer"
#: (PIN, İP) üzrə geniş tavan: 150 tələbə × 2 socket × ~3 yenidən qoşulma/dəq.
WS_CONNECT_IP_RATE_LIMIT_DEFAULT = "1000/1m"
#: Server auto-reveal taymerlərinin səpələnməsi (bir anda yüzlərlə DB cəhdi olmasın).
AUTO_REVEAL_JITTER_SECONDS = 0.75


def scope_ip(scope) -> str:
    """Müştəri İP-si — HTTP ilə EYNİ etibarlı-proxy qaydası (2026-10-08, ``core.asgi_scope``).

    Əvvəl ``scope["client"]`` idi: daphne ``--proxy-headers`` onu ``X-Forwarded-For``-un ƏN
    SOL (müştərinin yaza bildiyi) üzvündən qurur. İndi ``get_client_ip`` semantikası —
    sağdan ``TRUSTED_PROXY_HOPS``; başlıq yoxdursa ``scope["client"]``.
    """
    return scope_client_ip(scope) or "unknown"


def scope_cookies(scope) -> dict[str, str]:
    return scope.get("cookies") or {}


def scope_user_id(scope) -> int | None:
    user = scope.get("user")
    return user.id if getattr(user, "is_authenticated", False) else None


def signed_player_token(scope, pin: str) -> tuple[str | None, dict[str, Any] | None]:
    """``(token, payload)`` — payload yalnız imza + PIN uyğun gəlirsə (DB sorğusuz)."""
    token = scope_cookies(scope).get(PLAYER_COOKIE_NAME)
    return token, load_player_token_payload(token, pin=pin)


def connect_identity(scope, token_payload: dict[str, Any] | None) -> str:
    """Kimlik əsaslı limit açarı — eyni NAT İP-dəki tələbələr bir-birini bloklamır."""
    if token_payload is not None:
        client_id = str(token_payload.get("client_id") or "").strip()
        if client_id:
            return f"player-client:{client_id}"
        return f"player:{token_payload.get('player_id')}"
    user_id = scope_user_id(scope)
    if user_id:
        return f"user:{user_id}"
    live_client_id = str(scope_cookies(scope).get(LIVE_CLIENT_ID_COOKIE_NAME) or "").strip()
    if live_client_id:
        return f"viewer-client:{live_client_id[:64]}"
    return f"ip:{scope_ip(scope)}"


def connect_ip_rate() -> str:
    return getattr(settings, "LIVE_WS_CONNECT_IP_RATE_LIMIT", WS_CONNECT_IP_RATE_LIMIT_DEFAULT)


def decode_client_json(text_data: str | None) -> Any:
    try:
        return json.loads(text_data or "")
    except (TypeError, ValueError):
        return None


def merge_personal(data: dict[str, Any], event: dict[str, Any], player_id: int | None) -> dict[str, Any] | None:
    """Kanal hadisəsindəki ``personal`` xəritəsindən YALNIZ bu oyunçunun sətri.

    ``None`` — xəritə yoxdur (köhnə formatlı hadisə; çağıran DB-yə müraciət edə bilər).
    """
    personal = event.get("personal")
    if not isinstance(personal, dict) or player_id is None:
        return None
    raw = personal.get(str(player_id))
    if not raw:
        return dict(data)
    try:
        extras = json.loads(raw)
    except (TypeError, ValueError):
        return dict(data)
    return {**data, **extras} if isinstance(extras, dict) else dict(data)


def auto_reveal_delay(question: dict[str, Any] | None) -> tuple[int, float] | None:
    """``(question_id, saniyə)`` — serverin reveal cəhdinə qədər gözləmə (``None`` → taymer yoxdur)."""
    if not isinstance(question, dict):
        return None
    ends_at = question.get("ends_at")
    ends = parse_datetime(ends_at) if isinstance(ends_at, str) else ends_at
    if not isinstance(ends, datetime):
        return None
    try:
        question_id = int(question.get("id"))
    except (TypeError, ValueError):
        return None
    delay = (ends - timezone.now()).total_seconds() + SERVER_AUTO_REVEAL_GRACE_SECONDS
    return question_id, max(0.0, delay) + random.uniform(0, AUTO_REVEAL_JITTER_SECONDS)  # nosec B311
