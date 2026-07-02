"""Profil "unit-exams" bölməsi üçün context-fragment qurucusu.

Dekan/kafedra müdürü üçün öz alt-ağacının imtahanlarına oxu-only baxış. Data
scope-u ``organizations.scoping`` ilə.
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.accounts.views._helpers.formatting import _query_string
from apps.accounts.views._helpers.tenant import _get_active_organization


def _defaults() -> dict:
    return {
        "unit_exams_page_obj": None,
        "unit_exams_search_query": "",
        "unit_exams_total_count": 0,
        "unit_exams_pagination_query": "",
    }


def build_unit_exams_context(request, *, allowed_sections, active_section) -> dict:
    """Unit imtahanları bölməsi üçün ``context`` açarlarını qaytarır. Bölmə aktiv
    deyil / org yoxdur / istifadəçi unit-scoped deyilsə default dəyərlər (davranış
    köhnə inline blokla eyni)."""
    if not (active_section == "unit-exams" and "unit-exams" in allowed_sections):
        return _defaults()

    from apps.exams.models import Exam
    from apps.organizations.models import Membership, OrgUnit
    from apps.organizations.public import get_unit_scope

    org = _get_active_organization(request)
    if org is None:
        return _defaults()
    scope = get_unit_scope(request.user, org, request=request)
    if not scope.is_unit_scoped:
        return _defaults()

    unit_ids = OrgUnit.objects.filter(organization=org).filter(scope.unit_subtree_q())
    member_user_ids = Membership.objects.filter(
        organization=org,
        is_active=True,
        scope_unit__in=unit_ids.values("pk"),
    ).values("user_id")
    qs = (
        Exam.objects.filter(organization=org)
        .filter(Q(course__unit__in=unit_ids.values("pk")) | Q(author_id__in=member_user_ids))
        .select_related("author", "course")
        .annotate(attempts_total=Count("attempts", distinct=True))
        .order_by("-created_at")
    )
    search_query = (request.GET.get("unit_exam_q") or "").strip()[:120]
    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query)
            | Q(author__username__icontains=search_query)
            | Q(course__title__icontains=search_query)
        )
    return {
        "unit_exams_total_count": qs.count(),
        "unit_exams_page_obj": Paginator(qs, 10).get_page(request.GET.get("unit_exam_page")),
        "unit_exams_search_query": search_query,
        "unit_exams_pagination_query": _query_string(section="unit-exams", unit_exam_q=search_query),
    }
