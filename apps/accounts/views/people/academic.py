"""Tələbə idarəetməsinin OXU endpoint-ləri — kart, hədəf-qrup axtarışı, ön baxış.

Üç endpoint, üç fərqli tezliklə (``api.py``-dakı bölgü prinsipi ilə eyni):

* ``people_student_card`` — sətrin «İdarə et» düyməsinə basıldıqda BİR dəfə.
* ``people_academic_groups`` — hədəf qrup seçicisinin type-ahead axtarışı;
  səhifələnir (``offset``/``limit`` + ``has_more``), yəni bütün qruplar heç vaxt
  bir yerdə yüklənmir (``EMSSearchableSelect`` müqaviləsi).
* ``people_transfer_preview`` — qrup seçiləndə nəticənin ön baxışı; təsdiq
  düyməsi yalnız bu cavabdan sonra aktivləşir.

Hamısı fail-closed: icazə/scope olmadan ``has_access: false`` və ya 404.
Sətirlərdə PII YOXDUR — yalnız tələbənin adı (kartda onsuz da göstərilir) və
akademik metadata.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.services import people
from apps.accounts.services.rim.policy import RimAccessError

logger = logging.getLogger(__name__)

#: Qrup seçicisinin səhifə ölçüsü (searchable-select lazy scroll ilə uzanır).
GROUP_PAGE_DEFAULT = 20
GROUP_PAGE_MAX = 50
#: Axtarış sətrinin yuxarı həddi — uzun sorğu DB-yə ötürülmür.
MAX_QUERY_LENGTH = 80


def _error(exc: RimAccessError) -> JsonResponse:
    return JsonResponse({"has_access": False, "error": exc.reason_code, "message": exc.message}, status=exc.status)


@never_cache
@login_required
@require_GET
def people_student_card(request, user_id):
    """Tələbənin idarəetmə kartı — qeydlər, yazılışlar, mümkün əməllər."""
    actor = people.resolve_actor(request)
    try:
        payload = people.build_student_card(actor=actor, user_id=user_id, request=request)
    except RimAccessError as exc:
        return _error(exc)
    return JsonResponse(payload)


@never_cache
@login_required
@require_GET
def people_academic_groups(request):
    """Köçürmənin HƏDƏF qrupları — aktorun idarə sahəsində, axtarışlı/səhifəli.

    ``exclude`` parametri cari qrupu siyahıdan çıxarır: istifadəçi tələbəni
    olduğu qrupa «köçürə» bilməsin (servis onsuz da bloklayır, amma seçimdə
    görünməsi yanlış gözlənti yaradırdı).
    """
    actor = people.resolve_actor(request)
    groups = people.scoped_groups_qs(actor, request=request)

    query = (request.GET.get("q") or "").strip()[:MAX_QUERY_LENGTH]
    if query:
        groups = groups.filter(name__icontains=query)
    exclude = (request.GET.get("exclude") or "").strip()
    if exclude:
        groups = groups.exclude(pk=exclude)

    offset, limit = _bounds(request)
    window = list(groups.order_by("name").values("id", "name")[offset : offset + limit + 1])
    return JsonResponse(
        {
            "has_access": actor.can_manage_academic,
            "results": [{"id": str(row["id"]), "text": row["name"]} for row in window[:limit]],
            "has_more": len(window) > limit,
        }
    )


def _bounds(request):
    def _int(name, default):
        try:
            return int(request.GET.get(name, default))
        except (TypeError, ValueError):
            return default

    offset = max(0, _int("offset", 0))
    limit = max(1, min(_int("limit", GROUP_PAGE_DEFAULT), GROUP_PAGE_MAX))
    return offset, limit


@never_cache
@login_required
@require_GET
def people_transfer_preview(request, record_id):
    """Köçürmə nəticəsinin ön baxışı — heç nə yazmır (GET, təhlükəsiz metod)."""
    actor = people.resolve_actor(request)
    if not actor.can_manage_academic:
        return JsonResponse({"ok": False, "has_access": False, "error": "permission_denied"}, status=403)
    try:
        payload = people.preview_group_transfer(
            actor=actor,
            record_id=record_id,
            new_group_id=(request.GET.get("group") or "").strip(),
            request=request,
        )
    except RimAccessError as exc:
        return _error(exc)
    payload["has_access"] = True
    return JsonResponse(payload)


__all__ = [
    "GROUP_PAGE_DEFAULT",
    "GROUP_PAGE_MAX",
    "people_academic_groups",
    "people_student_card",
    "people_transfer_preview",
]
