"""«Müraciətlərim» bölməsinin YARDIMÇI JSON marşrutu.

Panelin bütün əsas əməlləri ``apps.applications``-ın öz JSON səthinə gedir
(`/muracietler/api/…`). Burada YALNIZ bir boşluq bağlanır: «Təyin et» dialoqunun
namizəd siyahısı. Siyahı domenə aiddir, ona görə məntiq modulun public fasadında
(``assignable_handlers``) qalır — bu view sadəcə HTTP qabığıdır.

FAIL-CLOSED: qapı əməl qapısı ilə eynidir (fasad ``access.can_act``-ə baxır);
əhatəsi olmayan aktor BOŞ siyahı alır, mövcudluq faktı sızmır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@login_required
@require_GET
def applications_assignees(request) -> JsonResponse:
    """Cari şöbəni əhatə edən emalçılar (dialoqun `select` siyahısı)."""
    from apps.accounts.views._helpers.tenant import _get_active_organization
    from apps.applications.public import assignable_handlers

    organization = _get_active_organization(request)
    application_id = (request.GET.get("application") or "").strip()
    if organization is None or not application_id:
        return JsonResponse({"ok": True, "results": []})
    try:
        results = assignable_handlers(request.user, organization, application_id)
    except (ValueError, TypeError):  # yararsız UUID — mövcudluq sızdırmadan boş
        results = []
    return JsonResponse({"ok": True, "results": results})


__all__ = ["applications_assignees"]
