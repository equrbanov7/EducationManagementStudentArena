"""«İntensiv kurs» dialoqunun axtarış endpoint-i — ``EMSSearchableSelect`` müqaviləsi (2026-10-25).

``GET /ders-yuku/intensiv/axtar/?kind=students|subjects|teachers&chair=<uuid>&q=…&offset=…`` →
``{"results": [{"id", "text", "hint"}], "has_more"}``. Qapı: intensiv kurs açmaq səlahiyyəti (kafedranın
``workload.distribute`` açarı və ya Tədris şöbəsinin ``workload.load_import``-u) — fail-closed.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, Value, When
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.search_text import tolerant_q

from ..services import WorkloadDenied, resolve_chair
from ..services.intensive import can_create
from ..services.people import teacher_pool
from ._base import active_organization, actor_for, denied, error, no_org

PAGE = 20


def _offset(request) -> int:
    try:
        return max(0, int(request.GET.get("offset") or 0))
    except ValueError:
        return 0


def _subjects(organization, chair, q, offset) -> dict:
    Subject = django_apps.get_model("registrar", "Subject")
    queryset = Subject.objects.filter(organization=organization, is_active=True)
    search = tolerant_q(q, ("name",), compact_fields=("code",))
    if search is not None:
        queryset = queryset.filter(search)
    # Kafedranın öz fənləri əvvəldə (``chair_unit``), sonra ad sırası.
    own_first = Case(When(chair_unit_id=chair.pk, then=Value(0)), default=Value(1), output_field=IntegerField())
    window = list(queryset.annotate(own=own_first).order_by("own", "name", "code")[offset : offset + PAGE + 1])
    return {
        "results": [
            {"id": str(item.pk), "text": f"{item.name} · {item.code}", "hint": item.code} for item in window[:PAGE]
        ],
        "has_more": len(window) > PAGE,
    }


def _teachers(organization, chair, q, offset) -> dict:
    pool = teacher_pool(organization, chair, search=q, limit=offset + PAGE + 1, include_outside=True)
    window = pool[offset : offset + PAGE + 1]
    return {
        "results": [
            {
                "id": item["id"],
                "text": item["full_name"],
                "hint": item.get("home_chair") or item.get("username", ""),
            }
            for item in window[:PAGE]
        ],
        "has_more": len(window) > PAGE,
    }


@never_cache
@login_required
@require_GET
def intensive_lookup(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    try:
        chair = resolve_chair(organization, request.GET.get("chair") or "")
    except WorkloadDenied as exc:
        return denied(exc)
    if not can_create(actor, chair.pk):
        return denied(WorkloadDenied("workload.forbidden", "İntensiv kurs açmaq səlahiyyətiniz yoxdur."))
    kind = (request.GET.get("kind") or "").strip()
    q = (request.GET.get("q") or "").strip()[:100]
    offset = _offset(request)
    if kind == "subjects":
        return JsonResponse(_subjects(organization, chair, q, offset))
    if kind == "teachers":
        return JsonResponse(_teachers(organization, chair, q, offset))
    if kind == "students":
        from apps.registrar.public import search_intensive_students

        return JsonResponse(search_intensive_students(organization=organization, q=q, offset=offset, limit=PAGE))
    return error("workload.invalid_kind", "Naməlum axtarış növü.")


__all__ = ["intensive_lookup"]
