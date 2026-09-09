"""«Registrar (kataloq)» bölməsinin JSON səthi (org-wide ``course.edit``).

Panel SERVER-RENDER-lidir; burada yalnız dialoqların əməlləri var:

* ``values`` — redaktə dialoqunu doldurmaq üçün mövcud sətrin dəyərləri;
* ``save``   — yaratma / redaktə (validasiya mövcud ``registrar/forms.py``-dədir).

Silmə YOXDUR: kataloq sətirləri «Aktiv» bayrağı ilə deaktiv edilir (yumşaq
silmə) — sahibin ümumi qaydası, səhvən silinən sətir bərpa oluna bilsin.

Bütün məntiq ``apps.registrar.catalog_console``-dadır; bu fayl yalnız tenant +
icazə qapısı və JSON çevirməsidir. FAIL-CLOSED: icazəsiz aktor 403, naməlum
`action` və ya `tab` 400.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar import catalog_console as console

_CTX = "registrar.catalog"

ALLOWED_ACTIONS = frozenset({"values", "save"})


def _organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


@login_required
@never_cache
@require_POST
def registrar_catalog_action(request):
    organization = _organization(request)
    if not console.can_manage(request.user, organization):
        return JsonResponse(
            {
                "ok": False,
                "error": "permission_denied",
                "message": pgettext(_CTX, "Akademik kataloqu idarə etmək üçün icazəniz yoxdur."),
            },
            status=403,
        )

    data = _payload(request)
    action = (data.get("action") or "").strip()
    tab = (data.get("tab") or "").strip()
    if action not in ALLOWED_ACTIONS or tab not in console.TAB_KEYS:
        return JsonResponse({"ok": False, "error": "bad_request"}, status=400)

    pk = (data.get("id") or "").strip()

    if action == "values":
        if not pk:
            return JsonResponse({"ok": False, "error": "bad_request"}, status=400)
        return JsonResponse({"ok": True, "values": console.entity_values(organization, tab=tab, pk=pk)})

    obj, errors = console.save(organization, tab=tab, pk=pk or None, data=data, actor=request.user)
    if errors:
        return JsonResponse({"ok": False, "error": "invalid", "errors": errors}, status=400)
    return JsonResponse({"ok": True, "id": str(obj.pk)})


__all__ = ["registrar_catalog_action"]
