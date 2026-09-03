"""RİM oxu endpoint-ləri — axtarış və istifadəçi detalı (JSON).

Hər ikisi ``@login_required`` + ``@never_cache`` + `user.search` icazə qapılıdır.
İcazə həlli `services.rim.policy`-dədir; view yalnız sorğunu oxuyub cavabı
serializasiya edir (fail-closed: icazə yoxdursa 403).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.services.rim import (
    PERM_SEARCH,
    RimAccessError,
    manageable_users_queryset,
    require_permission,
    resolve_actor,
    search_users,
    serialize_detail,
    serialize_row,
)

User = get_user_model()


def _error_response(exc: RimAccessError) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": exc.reason_code, "message": exc.message},
        status=exc.status,
    )


@never_cache
@login_required
@require_GET
def rim_user_search(request):
    """Ad + soyad + ata adı (və ya email/FİN/username) ilə istifadəçi axtarışı."""
    actor = resolve_actor(request)
    try:
        payload = search_users(
            actor,
            query=request.GET.get("q", ""),
            status=request.GET.get("status", "all"),
            page=request.GET.get("page", 1),
            page_size=request.GET.get("page_size", 20),
        )
    except RimAccessError as exc:
        return _error_response(exc)

    return JsonResponse(
        {
            "ok": True,
            "query": payload["query"],
            "status": payload["status"],
            "page": payload["page"],
            "num_pages": payload["num_pages"],
            "total": payload["total"],
            "has_next": payload["has_next"],
            "has_previous": payload["has_previous"],
            "results": [serialize_row(user, actor) for user in payload["results"]],
        }
    )


@never_cache
@login_required
@require_GET
def rim_user_detail(request, user_id):
    """Bir istifadəçinin detal kartı (rollar, status, mümkün əməliyyatlar)."""
    actor = resolve_actor(request)
    try:
        require_permission(actor, PERM_SEARCH)
    except RimAccessError as exc:
        return _error_response(exc)

    # Hədəf aktorun idarə sahəsindən KƏNARDIRSA 404 — mövcudluq sızdırılmır.
    target = manageable_users_queryset(actor).filter(pk=user_id).first()
    if target is None:
        return JsonResponse(
            {"ok": False, "error": "target_not_found", "message": "İstifadəçi tapılmadı."},
            status=404,
        )

    return JsonResponse({"ok": True, "user": serialize_detail(target, actor)})


__all__ = ["rim_user_detail", "rim_user_search"]
