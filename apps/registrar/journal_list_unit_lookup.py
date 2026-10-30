"""Jurnal bölmə seçiciləri siyahının öz journal.view əhatəsindən oxuyur."""

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.search_text import tolerant_q

from . import offering_chairs
from .journal_list_lookup import _bounds
from .journal_list_query import apply_unit_filters, faculty_department_choices_for
from .journal_list_scope import journal_list_base


def _search(request, kind):
    org = getattr(request, "organization", None)
    if org is None:
        return JsonResponse({"results": [], "has_more": False})
    base, broad = journal_list_base(request.user, request)
    if not broad:
        return JsonResponse({"results": [], "has_more": False})
    if kind != "faculty":
        base, _, _ = apply_unit_filters(base, org, request.GET.get("faculty", ""), "")
    if kind == "faculty":
        faculties, _ = faculty_department_choices_for(base)
        ids = [row["value"] for row in faculties]
    elif kind == "department":
        ids = offering_chairs.chair_candidates(base, org.pk)
    else:
        ids = base.order_by().values("group_id")
    units = django_apps.get_model("organizations", "OrgUnit").objects.filter(organization=org, pk__in=ids)
    query = tolerant_q(request.GET.get("q", ""), ("name",), compact_fields=("name",))
    if query is not None:
        units = units.filter(query)
    offset, limit = _bounds(request)
    rows = list(units.order_by("name", "pk").values("pk", "name")[offset : offset + limit + 1])
    return JsonResponse(
        {
            "results": [{"id": str(row["pk"]), "text": row["name"]} for row in rows[:limit]],
            "has_more": len(rows) > limit,
        }
    )


@never_cache
@login_required
@require_GET
def faculty_search(request):
    return _search(request, "faculty")


@never_cache
@login_required
@require_GET
def department_search(request):
    return _search(request, "department")


@never_cache
@login_required
@require_GET
def group_search(request):
    return _search(request, "group")
