"""«Universitet strukturu» — RƏHBƏR NAMİZƏDLƏRİ lookup-u (axtarışlı seçici üçün).

NİYƏ AYRICA ENDPOINT? Əvvəl bütün namizədlər (min. rol səviyyəsindən yuxarı hər
aktiv üzv) səhifə ilə birlikdə native `<select>`-ə render olunurdu. İri
təşkilatda bu yüzlərlə `<option>` deməkdir: siyahı uzun, axtarış yoxdur, native
popup dialoqun sərhədindən daşır. İndi siyahı ``EMSSearchableSelect`` ilə
SERVER-dən gəlir — debounce-lu axtarış + offset/limit səhifələmə.

Cavab forması layihədəki digər lookup-larla EYNİDİR (``guest_roster_views``,
``journal_lesson_lookup``)::

    {"results": [{"id": "<user id>", "text": "Ad Soyad — Rol"}], "has_more": bool}

QAPI iki qatdır və fail-closed-dur: struktur əhatəsi (``unit.view``) + rəhbər
təyini açarı (``unit.assign_head``) — yəni namizəd adlarını yalnız təyinat edə
bilən aktor görür.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from ..models import Organization
from ..views import _has_org_permission
from ._shared import head_candidate_memberships, head_candidate_rows
from .tree import tree_scope

#: Bir səhifədə neçə namizəd (infinite-scroll addımı).
PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def _bounds(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", PAGE_SIZE))
    except (TypeError, ValueError):
        limit = PAGE_SIZE
    return offset, max(1, min(limit, MAX_PAGE_SIZE))


def _label(row) -> str:
    return f"{row['full_name']} — {row['role_label']}" if row["role_label"] else row["full_name"]


@login_required
@require_GET
def structure_head_candidates(request, slug):
    """``?q=`` / ``?offset=`` / ``?limit=`` ilə rəhbər namizədləri."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    if not scope.has_structure_access or not _has_org_permission(request, "unit.assign_head"):
        # Fail-closed: səlahiyyətsiz aktora namizəd adları SIZMIR.
        return JsonResponse({"results": [], "has_more": False}, status=403)

    offset, limit = _bounds(request)
    memberships = head_candidate_memberships(organization, search=request.GET.get("q", ""))
    # Təkrarsızlaşdırma İSTİFADƏÇİ üzrədir (bir şəxsin bir neçə üzvlüyü ola bilər),
    # ona görə səhifə ÜZVLÜKDƏN deyil, təmizlənmiş sətirlərdən kəsilir. Pəncərə
    # `offset + limit + 1`-dən bir qədər geniş götürülür ki, təkrarlar
    # atıldıqdan sonra da səhifə dolsun.
    window = head_candidate_rows(memberships[: offset + (limit + 1) * 2])
    page = window[offset : offset + limit]
    return JsonResponse(
        {
            "results": [{"id": str(row["user_id"]), "text": _label(row)} for row in page],
            "has_more": len(window) > offset + limit,
        }
    )


__all__ = ["structure_head_candidates", "PAGE_SIZE"]
