"""«Alt qrupa tələbə əlavə et» — OXU endpoint-ləri (GET, JSON).

Hamısı fail-closed: açarsız aktor 403, əhatədən kənar tələbə 404. Domen sorğuları
``apps.registrar.public.subgroup_placement_lookups``-dadır (bu modul registrar modellərini import etmir).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import SubgroupPlacementError, subgroup_placement_history, subgroup_placement_lookups

from .policy import forbidden, resolve_actor

MAX_QUERY_LENGTH = 80


def _q(request) -> str:
    return (request.GET.get("q") or "").strip()[:MAX_QUERY_LENGTH]


def _flag(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "on", "yes")


def _error(exc: SubgroupPlacementError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=exc.status)


def _guarded(handler):
    """Aktor qapısı + domen xətasının JSON-a çevrilməsi (hər GET üçün eyni)."""

    @never_cache
    @login_required
    @require_GET
    def view(request, *args, **kwargs):
        actor = resolve_actor(request)
        if not actor.has_access:
            return forbidden()
        try:
            return JsonResponse(handler(request, actor, *args, **kwargs))
        except SubgroupPlacementError as exc:
            return _error(exc)

    view.__name__ = handler.__name__
    view.__doc__ = handler.__doc__
    return view


@_guarded
def placement_students(request, actor):
    """Addım 1 axtarışı — əhatədəki oxuyan tələbələr."""
    return subgroup_placement_lookups.search_students(
        actor=actor.user,
        organization=actor.organization,
        q=_q(request),
        offset=request.GET.get("offset"),
        limit=request.GET.get("limit"),
    )


@_guarded
def placement_student(request, actor, student_id):
    """Addım 1 — tələbənin qrupu, kredit yükü, kəsilmiş fənləri, yerləşdirmə tarixçəsi."""
    payload = subgroup_placement_lookups.student_summary(
        actor=actor.user, organization=actor.organization, student_id=student_id
    )
    payload["ok"] = True
    return payload


@_guarded
def placement_subjects(request, actor):
    """Addım 2 — fənn axtarışı (``?student=``)."""
    return subgroup_placement_lookups.search_subjects(
        actor=actor.user,
        organization=actor.organization,
        student_id=request.GET.get("student"),
        q=_q(request),
        offset=request.GET.get("offset"),
        limit=request.GET.get("limit"),
    )


@_guarded
def placement_offerings(request, actor):
    """Addım 2 — fənnin uyğun jurnalları (``?student=&subject=``)."""
    payload = subgroup_placement_lookups.offerings_for(
        actor=actor.user,
        organization=actor.organization,
        student_id=request.GET.get("student"),
        subject_id=_uuid(request.GET.get("subject")),
    )
    payload["ok"] = True
    return payload


@_guarded
def placement_preview(request, actor):
    """Addım 3-dən əvvəl — bütün yoxlamalar, heç nə yazılmır."""
    return subgroup_placement_lookups.preview(
        actor=actor.user,
        organization=actor.organization,
        student_id=request.GET.get("student"),
        offering_id=_uuid(request.GET.get("offering")),
        release_source=_flag(request.GET.get("release")),
    )


@_guarded
def placement_recent(request, actor):
    """«Son yerləşdirmələr» — əhatədəki yerləşdirmələr + geri götürmə izi."""
    return subgroup_placement_history.recent_placements(
        actor=actor.user,
        organization=actor.organization,
        q=_q(request),
        offset=_int(request.GET.get("offset")),
        limit=_int(request.GET.get("limit")) or subgroup_placement_history.PAGE_SIZE,
    )


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _int(value) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


__all__ = [
    "placement_offerings",
    "placement_preview",
    "placement_recent",
    "placement_student",
    "placement_students",
    "placement_subjects",
]
