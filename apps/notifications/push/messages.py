"""Bildiriş → FCM mesajı (``messages:send`` gövdəsindəki ``message`` obyekti).

Mətn ALICININ dilindədir: cihazın ``language``-ı (``ru-RU`` → ``ru``), yoxdursa / tanınmırsa kanonik dil (az) —
``localize_notification`` (``metadata.i18n`` deskriptoru) ilə; deskriptor yoxdursa saxlanan mətn.

``data`` (bütün dəyərlər SƏTİRDİR — FCM tələbi): ``notification_id``, ``type``, ``link`` (saytın nisbi yolu, deep
link), ``url`` (mütləq ünvan), ``created_at`` (ISO 8601). Mobil tətbiq toxunuşda ``link``/``url``-i açır və
``POST /api/notifications/<id>/read/`` ilə «oxundu» edir. Sxem: ``docs/api/PUSH_NOTIFICATIONS.md``.
"""

from __future__ import annotations

import copy

from django.conf import settings

ANDROID_CHANNEL_ID = "ems_notifications"
TITLE_LIMIT = 200
BODY_LIMIT = 1000


def normalize_language(value) -> str:
    """``ru-RU`` / ``RU`` / ``ru_RU`` → ``ru``; dəstəklənməyən / boş → kanonik dil."""
    from apps.notifications.i18n import all_languages

    code = str(value or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in all_languages() else settings.LANGUAGE_CODE


def absolute_url(link: str) -> str:
    link = (link or "").strip()
    if not link or link.startswith(("http://", "https://")):
        return link
    # Telefon kənar şəbəkədədir: LAN IP-li SITE_URL açılmır — əvvəl publik domen (DOCUMENT_VERIFY_BASE_URL ilə eyni).
    base = next(
        (
            str(value).strip().rstrip("/")
            for value in (
                getattr(settings, "PUSH_LINK_BASE_URL", ""),
                getattr(settings, "DOCUMENT_VERIFY_BASE_URL", ""),
                getattr(settings, "SITE_URL", ""),
            )
            if value and str(value).strip()
        ),
        "",
    )
    return f"{base}/{link.lstrip('/')}" if base else link


def localized_text(notification, language: str) -> tuple[str, str]:
    """``(title, body)`` — ``language`` dilində; obyektin özü DƏYİŞMİR."""
    from apps.notifications.i18n import localize_notification

    clone = localize_notification(copy.copy(notification), language)
    title = (clone.title or getattr(settings, "SITE_BRAND_NAME", "") or "EMS Arena").strip()
    body = (clone.message or "").strip()
    return title[:TITLE_LIMIT], body[:BODY_LIMIT]


def build_message(*, token: str, platform: str, notification, title: str, body: str, unread: int) -> dict:
    link = notification.link or ""
    url = absolute_url(link)
    created = getattr(notification, "created_at", None)
    data = {
        "notification_id": str(notification.pk),
        "type": str(notification.notification_type or ""),
        "link": link,
        "url": url,
        "created_at": created.isoformat() if created else "",
    }
    content = {"title": title}
    if body:
        content["body"] = body
    message = {
        "token": token,
        "notification": content,
        "data": data,
        "android": {
            "priority": "high",
            "notification": {"channel_id": ANDROID_CHANNEL_ID, "tag": f"ems-{notification.pk}"},
        },
        "apns": {
            "headers": {"apns-priority": "10"},
            "payload": {"aps": {"sound": "default", "badge": max(0, int(unread)), "thread-id": data["type"] or "ems"}},
        },
    }
    if platform == "web" and url.startswith("https://"):
        message["webpush"] = {"fcm_options": {"link": url}}
    return message


__all__ = ["ANDROID_CHANNEL_ID", "absolute_url", "build_message", "localized_text", "normalize_language"]
