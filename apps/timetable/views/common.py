"""Səhifələrin ortaq konteksti — naviqasiya, semestr seçicisi, JSON köməkçiləri."""

from __future__ import annotations

import json

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext

from ..services import access

_CTX = "timetable.nav"


def payload(request) -> dict:
    """JSON gövdəsi (``EMSCore.fetchJSON``) və ya forma POST-u → dict."""
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:  # UnicodeDecodeError da ValueError-dur
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


def json_error(code, message, *, status=400, **extra):
    return JsonResponse({"ok": False, "error": code, "message": str(message), **extra}, status=status)


def api_organization(request):
    """JSON endpoint-lər üçün: icazə yoxdursa ``(None, 403 cavabı)``."""
    try:
        return access.organization_for(request), None
    except PermissionDenied:
        return None, json_error(
            "permission_denied", pgettext(_CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."), status=403
        )


def base_context(request, organization, period, active) -> dict:
    period_id = str(period.pk) if period is not None else ""
    suffix = f"?period={period_id}" if period_id else ""
    nav = [
        ("home", "timetable:home", "fa-layer-group", pgettext(_CTX, "İşləmələr")),
        ("availability", "timetable:availability", "fa-user-clock", pgettext(_CTX, "Müəllim əlçatanlığı")),
        ("policies", "timetable:policies", "fa-sun", pgettext(_CTX, "Növbələr")),
        ("new", "timetable:new_run", "fa-wand-magic-sparkles", pgettext(_CTX, "Yeni işləmə")),
    ]
    return {
        "tt_active": active,
        "tt_period": period,
        "tt_period_id": period_id,
        "tt_period_choices": access.period_choices(organization),
        "tt_nav": [
            {"key": key, "url": reverse(name) + suffix, "icon": icon, "label": label, "is_active": key == active}
            for key, name, icon, label in nav
        ],
        "tt_editor_url": reverse("accounts:profile") + "?section=schedule-manage",
        "active_main_nav": "schedule",
    }


__all__ = ["api_organization", "base_context", "json_error", "payload"]
