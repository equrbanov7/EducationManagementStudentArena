"""JSON səthin ortaq qabığı: giriş qapısı, xəta formatı, obyekt tapılması."""

from __future__ import annotations

import functools

from django.core.exceptions import ValidationError
from django.http import JsonResponse

from ..models import Application
from ..services import access
from ..state_machine import TransitionDenied

#: Xəta cavabı: ``{"ok": false, "errors": {"<sahə>": ["mətn", …]}}``
#: Sahəyə bağlanmayan xəta üçün açar ``__all__``.
GLOBAL_ERROR_KEY = "__all__"


def error(errors, status: int = 400) -> JsonResponse:
    if isinstance(errors, str):
        errors = {GLOBAL_ERROR_KEY: [errors]}
    return JsonResponse({"ok": False, "errors": errors}, status=status)


def ok(payload=None, **extra) -> JsonResponse:
    body = {"ok": True}
    if payload:
        body.update(payload)
    body.update(extra)
    return JsonResponse(body)


def json_endpoint(view):
    """Giriş + təşkilat konteksti qapısı; domen istisnalarını JSON-a çevirir."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return error("Giriş tələb olunur.", status=403)
        organization = getattr(request, "organization", None)
        if organization is None:
            return error("Aktiv təşkilat konteksti yoxdur.", status=403)
        try:
            return view(request, *args, organization=organization, **kwargs)
        except TransitionDenied as exc:
            status = 403 if exc.code.startswith("permission.") else 400
            return error({GLOBAL_ERROR_KEY: [str(exc)], "code": [exc.code]}, status=status)
        except ValidationError as exc:
            payload = exc.message_dict if hasattr(exc, "message_dict") else {GLOBAL_ERROR_KEY: exc.messages}
            return error(payload)

    return wrapper


def load_application(request, organization, application_id):
    """Müraciəti yükləyir və GÖRÜNÜŞ qapısını tətbiq edir.

    Tapılmayan və görünməyən sətir EYNİ cavabı verir (404) — mövcudluq faktı
    sızmasın deyə.
    """
    application = (
        Application.objects.filter(organization=organization, pk=application_id)
        .select_related("kind", "current_unit", "current_scope_unit", "created_by", "assigned_to", "organization")
        .first()
    )
    if application is None or not access.can_view(request.user, application):
        return None
    return application


__all__ = ["GLOBAL_ERROR_KEY", "error", "json_endpoint", "load_application", "ok"]
