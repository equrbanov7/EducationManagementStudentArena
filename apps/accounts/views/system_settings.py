"""«Sistem tənzimləmələri» — saxlama endpoint-i (sahib 2026-10-03). Qapı: RİM rəhbəri / superadmin."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.services import runtime_settings_admin

_CTX = "accounts.runtime_settings"


@never_cache
@login_required
@require_POST
def system_settings_save(request):
    if not runtime_settings_admin.can_manage(request.user, request):
        return JsonResponse(
            {"ok": False, "error": "forbidden", "message": pgettext(_CTX, "Bu əməl yalnız RİM rəhbəri üçündür.")},
            status=403,
        )
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            data = {}
    else:
        data = {key: value for key, value in request.POST.items()}
    if not isinstance(data, dict):
        data = {}
    try:
        result = runtime_settings_admin.save_values(actor=request.user, data=data, request=request)
    except runtime_settings_admin.RuntimeSettingsError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": "invalid",
                "errors": exc.errors,
                "message": pgettext(_CTX, "Bəzi dəyərlər yanlışdır."),
            },
            status=400,
        )
    count = len(result["changed"])
    message = (
        pgettext(_CTX, "Yadda saxlanıldı: %(n)d dəyişiklik. Bütün serverlərdə 10–15 saniyəyə qüvvəyə minir.")
        % {"n": count}
        if count
        else pgettext(_CTX, "Dəyişiklik yoxdur.")
    )
    return JsonResponse({"ok": True, "changed": result["changed"], "message": message})


__all__ = ["system_settings_save"]
