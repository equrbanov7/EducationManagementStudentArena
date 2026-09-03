"""«Müəllimlər» / «Tələbələr» kataloqunun OXU endpoint-ləri (JSON).

Üç endpoint, üç fərqli yenilənmə tezliyi ilə — QƏSDƏN ayrılıb:

* ``people_list``    — cədvəl sətirləri; hər filtr/səhifə klikində çağırılır.
* ``people_options`` — filtr açılışları + səbət sayları; nadir dəyişir, ona görə
  cədvəllə birlikdə çağırılmır (əks halda hər səhifə keçidi lüğət sorğularını
  təkrarlayardı — `academic_records` presedenti).
* ``people_detail``  — bir şəxsin kartı; yalnız sətrə klikləndikdə.

Hamısı fail-closed: aktor icazəsi olmadan ``has_access: false`` və boş data.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.services import people
from apps.accounts.services.people.constants import (
    DEFAULT_PAGE_SIZE,
    STUDENT_SORT_OPTIONS,
    TEACHER_SORT_OPTIONS,
)
from apps.accounts.services.rim.policy import RimAccessError

logger = logging.getLogger(__name__)

_EMPTY_LIST = {
    "has_access": False,
    "results": [],
    "page": 1,
    "num_pages": 1,
    "total": 0,
    "has_next": False,
    "has_previous": False,
}


def _filters_for(request, kind):
    sort_options = TEACHER_SORT_OPTIONS if kind == "teachers" else STUDENT_SORT_OPTIONS
    return people.parse_filters(request.GET, sort_options=sort_options, default_page_size=DEFAULT_PAGE_SIZE)


@never_cache
@login_required
@require_GET
def people_list(request, kind: str):
    """Səhifələnmiş kataloq cədvəli. ``kind`` — ``teachers`` / ``students``."""
    if kind not in ("teachers", "students"):
        return JsonResponse({**_EMPTY_LIST, "error": "unknown_catalog"}, status=404)

    actor = people.resolve_actor(request)
    filters = _filters_for(request, kind)

    if kind == "teachers":
        payload = people.build_teachers_page(actor=actor, filters=filters, request=request)
    else:
        payload = people.build_students_page(actor=actor, filters=filters, request=request)

    payload["capabilities"] = _capabilities(actor)
    return JsonResponse(payload)


@never_cache
@login_required
@require_GET
def people_options(request, kind: str):
    """Filtr açılışları (fakültə/kafedra/qrup/ixtisas/fənn/il) + səbət sayları."""
    if kind not in ("teachers", "students"):
        return JsonResponse({"has_access": False, "error": "unknown_catalog"}, status=404)

    actor = people.resolve_actor(request)
    filters = _filters_for(request, kind)
    payload = people.build_filter_options(actor=actor, kind=kind, filters=filters, request=request)
    return JsonResponse(payload)


@never_cache
@login_required
@require_GET
def people_detail(request, user_id):
    """Bir şəxsin detal kartı — yalnız aktorun görünüş sahəsindəki hesab üçün."""
    actor = people.resolve_actor(request)
    try:
        payload = people.build_detail(actor=actor, user_id=user_id, request=request)
    except RimAccessError as exc:
        return JsonResponse(
            {"has_access": False, "error": exc.reason_code, "message": exc.message},
            status=exc.status,
        )
    payload["capabilities"] = _capabilities(actor)
    return JsonResponse(payload)


def _capabilities(actor) -> dict:
    return {
        "can_view_teachers": actor.can_view_teachers,
        "can_view_students": actor.can_view_students,
        "can_view_contacts": actor.can_view_contacts,
        "can_view_demographics": actor.can_view_demographics,
        "can_manage_status": actor.can_manage_status,
        "can_manage_teacher_role": actor.can_manage_teacher_role,
    }


__all__ = ["people_detail", "people_list", "people_options"]
