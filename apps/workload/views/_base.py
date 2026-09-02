"""JSON endpoint-lərin ortaq köməkçiləri (aktor, org, gövdə, xəta çevrilməsi)."""

from __future__ import annotations

import json

from django.http import JsonResponse

from ..services import WorkloadDenied, resolve_actor


def active_organization(request):
    """Middleware-in həll etdiyi aktiv təşkilat (``OrganizationMiddleware``)."""
    return getattr(request, "organization", None)


def actor_for(request):
    return resolve_actor(request.user, active_organization(request), request=request)


def json_body(request) -> dict:
    """POST gövdəsi — JSON və ya form-encoded."""
    content_type = (request.META.get("CONTENT_TYPE") or "").split(";")[0].strip()
    if content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {key: value for key, value in request.POST.items()}


def denied(exc: WorkloadDenied, status: int = 403) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=status)


def error(code: str, message: str = "", status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": code, "message": message or code}, status=status)


def no_org() -> JsonResponse:
    return error("workload.no_organization", "Aktiv təşkilat seçilməyib.", status=409)


__all__ = ["active_organization", "actor_for", "denied", "error", "json_body", "no_org"]
