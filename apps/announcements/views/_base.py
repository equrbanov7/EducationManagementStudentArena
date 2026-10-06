"""JSON səthin ortaq qabığı (``applications/views/_base`` ilə eyni müqavilə)."""

from __future__ import annotations

import functools
import json

from django.http import JsonResponse
from django.utils.translation import pgettext

GLOBAL_ERROR_KEY = "__all__"


def error(errors, status: int = 400) -> JsonResponse:
    if isinstance(errors, str):
        errors = {GLOBAL_ERROR_KEY: [errors]}
    return JsonResponse({"ok": False, "errors": errors}, status=status)


def ok(**payload) -> JsonResponse:
    return JsonResponse({"ok": True, **payload})


def json_body(request) -> dict:
    """JSON gövdə (``EMSCore.fetchJSON``) və ya form-encoded POST — hər ikisi qəbul olunur."""
    if (request.content_type or "").startswith("application/json"):
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST


def member_endpoint(view):
    """Giriş + aktiv təşkilat qapısı (JSON cavab)."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return error(pgettext("announcements.api", "Giriş tələb olunur."), status=403)
        if getattr(request, "organization", None) is None:
            return error(pgettext("announcements.api", "Aktiv təşkilat konteksti yoxdur."), status=403)
        return view(request, *args, **kwargs)

    return wrapper


__all__ = ["GLOBAL_ERROR_KEY", "error", "json_body", "member_endpoint", "ok"]
