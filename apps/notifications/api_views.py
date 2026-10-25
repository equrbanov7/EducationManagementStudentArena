"""Mobil tətbiq üçün bildiriş JSON API-si — ``/api/notifications/`` (sahib 2026-10-25).

Autentifikasiya saytın özü ilədir (Django sessiya kukisi ``sessionid``); yazı sorğuları (POST/DELETE)
``X-CSRFToken`` başlığı (``csrftoken`` kukisindən) tələb edir. Girişsiz sorğu → ``401 {"error": "auth_required"}``
(login səhifəsinə yönləndirmə YOX — tətbiq JSON gözləyir). Sənəd: ``docs/api/PUSH_NOTIFICATIONS.md``.

Uclar:
  GET    /api/notifications/                    — siyahı (oxuyanın dilində), ``unread_count``
  GET    /api/notifications/unread-count/       — oxunmamış say
  POST   /api/notifications/<id>/read/          — «oxundu» (telefonda toxunanda — kabinetlə sinxron)
  POST   /api/notifications/read-all/           — hamısı oxundu
  GET    /api/notifications/devices/            — bu istifadəçinin aktiv cihazları + push vəziyyəti
  POST   /api/notifications/devices/            — cihaz qeydiyyatı (idempotent; token yenilənəndə də)
  DELETE /api/notifications/devices/            — çıxış: cihaz deaktiv (gövdədə ``token``)
  POST   /api/notifications/devices/test/       — özümə test push (yalnız superadmin / RİM)
"""

from __future__ import annotations

import json
import logging
from functools import wraps

from django.http import JsonResponse
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.notifications.models import InAppNotification, NotificationType
from apps.notifications.public_exports import localize_notification
from apps.notifications.push import config as push_config
from apps.notifications.push import devices as push_devices
from apps.notifications.push.messages import absolute_url, normalize_language
from apps.notifications.services import (
    get_unread_count,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from core.rate_limit import record_rate_limit_hit
from core.rls import bypass_rls

logger = logging.getLogger(__name__)

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 50
DEVICE_WRITE_RATE = "60/1h"
TEST_PUSH_RATE = "10/1h"
_TEST_ROLES = ("ikt_rehber", "rim_staff")


def _error(code: str, status: int, **extra) -> JsonResponse:
    return JsonResponse({"ok": False, "error": code, **extra}, status=status)


def api_login_required(view):
    """``login_required``-in JSON variantı: girişsiz → 401 (yönləndirmə yox)."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return _error("auth_required", 401)
        return view(request, *args, **kwargs)

    return _wrapped


def _json_body(request) -> dict:
    try:
        data = json.loads((request.body or b"{}").decode("utf-8") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _int_param(request, name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.GET.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _reader_language(request) -> str:
    """``?lang=`` (tətbiqin dili) → yoxdursa sorğunun aktiv dili (kuki / Accept-Language)."""
    requested = request.GET.get("lang")
    return normalize_language(requested or translation.get_language())


def _item(notification) -> dict:
    return {
        "id": notification.pk,
        "type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "link": notification.link,
        "url": absolute_url(notification.link),
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


# ───────────────────────────── bildiriş qutusu ─────────────────────────────


@never_cache
@api_login_required
@require_GET
def notification_list(request):
    page = _int_param(request, "page", 1, 1, 10_000)
    size = _int_param(request, "page_size", PAGE_SIZE_DEFAULT, 1, PAGE_SIZE_MAX)
    filter_by = request.GET.get("filter", "all")
    if filter_by not in {"all", "unread", "read"}:
        filter_by = "all"
    notification_type = request.GET.get("type", "")
    if notification_type and notification_type not in NotificationType.values:
        notification_type = ""
    start = (page - 1) * size
    with bypass_rls():  # recipient=user sərhəddir — bütün təşkilatların bildirişləri
        rows = list(
            get_user_notifications(user=request.user, filter_by=filter_by, notification_type=notification_type)[
                start : start + size + 1
            ]
        )
    language = _reader_language(request)
    items = [_item(localize_notification(row, language)) for row in rows[:size]]
    return JsonResponse(
        {
            "ok": True,
            "results": items,
            "page": page,
            "page_size": size,
            "has_next": len(rows) > size,
            "unread_count": get_unread_count(user=request.user),
            "language": language,
        }
    )


@never_cache
@api_login_required
@require_GET
def notification_unread_count(request):
    return JsonResponse({"ok": True, "unread_count": get_unread_count(user=request.user)})


@api_login_required
@require_POST
def notification_read(request, pk):
    with bypass_rls():
        notification = InAppNotification.objects.filter(pk=pk, recipient=request.user, deleted_at__isnull=True).first()
    if notification is None:
        return _error("not_found", 404)
    changed = mark_notification_read(notification=notification, user=request.user)
    return JsonResponse({"ok": True, "changed": changed, "unread_count": get_unread_count(user=request.user)})


@api_login_required
@require_POST
def notification_read_all(request):
    updated = mark_all_notifications_read(user=request.user)
    return JsonResponse({"ok": True, "updated": updated, "unread_count": 0})


# ───────────────────────────── cihazlar (push) ─────────────────────────────


def _push_state() -> dict:
    return {"configured": push_config.is_configured(), "enabled": push_config.push_enabled()}


def _rate_limited(scope: str, rate: str, user) -> bool:
    limited, _retry = record_rate_limit_hit(scope, rate, user.pk)
    return bool(limited)


@never_cache
@api_login_required
@require_http_methods(["GET", "POST", "DELETE"])
def devices(request):
    if request.method == "GET":
        rows = push_devices.user_devices(user=request.user)
        return JsonResponse(
            {"ok": True, "push": _push_state(), "devices": [push_devices.device_payload(row) for row in rows]}
        )
    if _rate_limited("notifications.push_device", DEVICE_WRITE_RATE, request.user):
        return _error("rate_limited", 429)
    data = _json_body(request)
    try:
        if request.method == "DELETE":
            changed = push_devices.unregister_device(user=request.user, token=data.get("token"))
            return JsonResponse({"ok": True, "deactivated": changed})
        device, created = push_devices.register_device(
            user=request.user,
            token=data.get("token"),
            platform=data.get("platform"),
            app_version=data.get("app_version", ""),
            language=data.get("language", ""),
            muted_types=data.get("muted_types"),
        )
    except push_devices.DeviceError as exc:
        return _error(exc.code, 400)
    return JsonResponse(
        {"ok": True, "created": created, "push": _push_state(), "device": push_devices.device_payload(device)},
        status=201 if created else 200,
    )


def _can_send_test(request) -> bool:
    user = request.user
    if getattr(user, "is_superuser", False):
        return True
    organization = getattr(request, "organization", None)
    if organization is None:
        return False
    from apps.organizations.public import user_has_org_role

    return bool(user_has_org_role(user, organization, _TEST_ROLES))


@api_login_required
@require_POST
def device_test(request):
    """Özümə test push — mobil komanda / RİM FCM qoşulmasını yoxlayır (bildiriş qutusuna yazılmır)."""
    if not _can_send_test(request):
        return _error("forbidden", 403)
    if _rate_limited("notifications.push_test", TEST_PUSH_RATE, request.user):
        return _error("rate_limited", 429)
    from django.utils.translation import pgettext

    from apps.notifications.push.dispatch import send_test

    title = pgettext("notifications.push", "Test bildirişi")
    body = pgettext("notifications.push", "Push bildirişləri bu cihazda işləyir.")
    report = send_test(user=request.user, title=title, body=body)
    return JsonResponse({"ok": True, "report": report})


__all__ = [
    "api_login_required",
    "device_test",
    "devices",
    "notification_list",
    "notification_read",
    "notification_read_all",
    "notification_unread_count",
]
