"""Profil "statistics" bölməsi üçün context-fragment qurucusu.

`build_statistics_section` ya AJAX AI-summary üçün `JsonResponse` (erkən-return),
ya da statistics_* context açarlarının dict-ini qaytarır. Davranış köhnə inline
blokla eynidir; şərti təyin olunan çıxışlar başda default-la ilkinləşdirilir.
"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse  # noqa: F401  (tip yoxlaması üçün caller-də istifadə olunur)

from apps.accounts.views._helpers.formatting import _query_string
from apps.accounts.views._helpers.tenant import _get_active_organization
from apps.courses.models import Course


def build_statistics_section(request, *, capabilities):
    statistics_courses = []
    statistics_groups = []
    statistics_organizations = []
    statistics_unit_layout = False
    statistics_org_page = None
    statistics_teacher_page = None
    statistics_course_page = None
    statistics_group_page = None
    statistics_teacher_course_page = None
    statistics_org_rows = []
    statistics_teacher_rows = []
    statistics_course_rows = []
    statistics_group_rows = []
    statistics_teacher_course_rows = []
    statistics_org_pagination_query = ""
    statistics_teacher_pagination_query = ""
    statistics_course_pagination_query = ""
    statistics_group_pagination_query = ""
    statistics_teacher_course_pagination_query = ""
    statistics_org_page_param = "stats_org_page"
    statistics_teacher_page_param = "stats_teacher_page"
    statistics_course_page_param = "stats_course_page"
    statistics_group_page_param = "stats_group_page"
    statistics_teacher_course_page_param = "stats_teacher_course_page"

    from apps.accounts.services.statistics_selectors import (
        get_org_admin_statistics,
        get_student_statistics,
        get_superadmin_statistics,
        get_teacher_statistics,
    )
    from apps.organizations.models import Organization as _StatisticsOrganization

    stat_org = _get_active_organization(request)
    statistics_content_type = (request.GET.get("stat_content_type") or "all").strip().lower()
    if statistics_content_type not in {"all", "exam", "assignment", "lab", "project"}:
        statistics_content_type = "all"
    statistics_filters = {
        "date_from": (request.GET.get("stat_date_from") or "").strip(),
        "date_to": (request.GET.get("stat_date_to") or "").strip(),
        "course": (request.GET.get("stat_course") or "").strip() or None,
        "group": (request.GET.get("stat_group") or "").strip() or None,
        "content_type": statistics_content_type,
        "organization": (request.GET.get("stat_organization") or "").strip() or None,
    }
    if not capabilities["is_superadmin"]:
        statistics_filters["organization"] = None

    selected_statistics_org = None
    if capabilities["is_superadmin"] and statistics_filters["organization"]:
        selected_statistics_org = (
            _StatisticsOrganization.objects.filter(
                id=statistics_filters["organization"],
                is_active=True,
                status="active",
            )
            .only("id", "name")
            .first()
        )
        if selected_statistics_org is None:
            statistics_filters["organization"] = None

    statistics_scope_org = selected_statistics_org or stat_org

    # Unit scoping (Faza 2): dekan/kafedra müdürü statistikaları yalnız öz
    # fakültə/kafedra alt-ağacı üzrə görür. Alt-ağac id-ləri bir dəfə
    # hesablanır və həm filtr seçimlərinə, həm selector-a ötürülür.
    statistics_scoped_unit_ids = None
    if stat_org and not capabilities["is_superadmin"]:
        from apps.organizations.models import OrgUnit as _StatOrgUnit
        from apps.organizations.public import get_unit_scope as _get_unit_scope

        _stat_unit_scope = _get_unit_scope(request.user, stat_org, request=request)
        if _stat_unit_scope.is_unit_scoped:
            statistics_scoped_unit_ids = list(
                _StatOrgUnit.objects.filter(organization=stat_org)
                .filter(_stat_unit_scope.unit_subtree_q())
                .values_list("pk", flat=True)
            )

    statistics_uses_personal_scope = not (
        capabilities["is_superadmin"]
        or capabilities["is_org_admin"]
        or capabilities["is_teacher"]
        or (capabilities.get("is_tutor") and stat_org and statistics_scoped_unit_ids is not None)
    )

    # Populate filter options
    if statistics_scope_org and not capabilities["is_superadmin"]:
        statistics_course_qs = Course.objects.filter(organization=statistics_scope_org)
        if statistics_uses_personal_scope:
            statistics_course_qs = statistics_course_qs.filter(
                memberships__user=request.user,
                memberships__role="student",
            )
        elif capabilities["is_teacher"] and not capabilities["is_org_admin"]:
            statistics_course_qs = statistics_course_qs.filter(owner=request.user)
        if statistics_scoped_unit_ids is not None:
            statistics_course_qs = statistics_course_qs.filter(unit_id__in=statistics_scoped_unit_ids)
        statistics_courses = list(statistics_course_qs.order_by("title").values("id", "title").distinct()[:100])
        allowed_course_ids = {str(row["id"]) for row in statistics_courses}
        if statistics_filters["course"] and statistics_filters["course"] not in allowed_course_ids:
            statistics_filters["course"] = None
    elif capabilities["is_superadmin"]:
        statistics_organizations = list(
            _StatisticsOrganization.objects.filter(is_active=True, status="active")
            .order_by("name")
            .values("id", "name")[:150]
        )
        superadmin_course_qs = Course.objects.all()
        if selected_statistics_org:
            superadmin_course_qs = superadmin_course_qs.filter(organization=selected_statistics_org)
        statistics_courses = list(superadmin_course_qs.order_by("title").values("id", "title")[:150])

    if statistics_scope_org:
        from apps.exams.models import StudentGroup as _SG

        statistics_group_qs = _SG.objects.filter(organization=statistics_scope_org)
        if statistics_uses_personal_scope:
            statistics_group_qs = statistics_group_qs.filter(students=request.user)
        elif capabilities["is_teacher"] and not capabilities["is_org_admin"] and not capabilities["is_superadmin"]:
            statistics_group_qs = statistics_group_qs.filter(Q(teacher=request.user) | Q(teachers=request.user))
        statistics_groups = list(statistics_group_qs.order_by("name").values("id", "name").distinct()[:100])
        allowed_group_ids = {str(row["id"]) for row in statistics_groups}
        if statistics_filters["group"] and statistics_filters["group"] not in allowed_group_ids:
            statistics_filters["group"] = None

    statistics_has_active_filters = any(
        [
            statistics_filters["date_from"],
            statistics_filters["date_to"],
            statistics_filters["course"],
            statistics_filters["group"],
            statistics_filters["organization"],
            statistics_filters["content_type"] != "all",
        ]
    )

    # Dashboard statistics are expensive (~44 aggregate queries) but do not
    # need to be real-time, so each (role, scope, filters) result is cached
    # briefly via core.cache.get_or_set_cached_statistics (FAZA 12).
    from core.cache import get_or_set_cached_statistics

    if capabilities["is_superadmin"]:
        statistics_data = get_or_set_cached_statistics(
            role="superadmin",
            scope_id="global",
            filters=statistics_filters,
            compute=lambda: get_superadmin_statistics(filters=statistics_filters),
        )
    elif capabilities["is_org_admin"]:
        if stat_org:
            if statistics_scoped_unit_ids is not None:
                # Dekan/kafedra müdürü — unit-scoped statistika. Cache açarı
                # istifadəçinin alt-ağacına görə ayrılır ki, rektorun org-wide
                # nəticəsi ilə qarışmasın (data sızması olmasın).
                _scoped_ids = statistics_scoped_unit_ids
                statistics_data = get_or_set_cached_statistics(
                    role="unit_manager",
                    scope_id=f"{stat_org.pk}:{request.user.pk}",
                    filters=statistics_filters,
                    compute=lambda: get_org_admin_statistics(
                        organization=stat_org,
                        filters=statistics_filters,
                        scoped_unit_ids=_scoped_ids,
                    ),
                )
            else:
                statistics_data = get_or_set_cached_statistics(
                    role="org_admin",
                    scope_id=stat_org.pk,
                    filters=statistics_filters,
                    compute=lambda: get_org_admin_statistics(organization=stat_org, filters=statistics_filters),
                )
    elif capabilities["is_teacher"]:
        statistics_data = get_or_set_cached_statistics(
            role="teacher",
            scope_id=request.user.pk,
            filters={**statistics_filters, "_org": getattr(stat_org, "pk", None)},
            compute=lambda: get_teacher_statistics(request.user, organization=stat_org, filters=statistics_filters),
        )
    elif capabilities.get("is_tutor") and stat_org and statistics_scoped_unit_ids is not None:
        # Tyutor — öz alt-ağacının qrup statistikası (unit_manager rejimi,
        # öz cache açarı ilə).
        statistics_unit_layout = True
        _tutor_scoped_ids = statistics_scoped_unit_ids
        statistics_data = get_or_set_cached_statistics(
            role="unit_manager",
            scope_id=f"{stat_org.pk}:{request.user.pk}",
            filters=statistics_filters,
            compute=lambda: get_org_admin_statistics(
                organization=stat_org,
                filters=statistics_filters,
                scoped_unit_ids=_tutor_scoped_ids,
            ),
        )
    else:
        # Student / lead student / member
        statistics_data = get_or_set_cached_statistics(
            role="student",
            scope_id=request.user.pk,
            filters={**statistics_filters, "_org": getattr(stat_org, "pk", None)},
            compute=lambda: get_student_statistics(request.user, organization=stat_org, filters=statistics_filters),
        )

    statistics_base_query = _query_string(
        section="statistics",
        stat_date_from=statistics_filters["date_from"],
        stat_date_to=statistics_filters["date_to"],
        stat_course=statistics_filters["course"],
        stat_group=statistics_filters["group"],
        stat_content_type=(None if statistics_filters["content_type"] == "all" else statistics_filters["content_type"]),
        stat_organization=statistics_filters["organization"],
    )

    if statistics_data.get("org_comparison"):
        statistics_org_page = Paginator(statistics_data["org_comparison"], 8).get_page(
            request.GET.get(statistics_org_page_param)
        )
        statistics_org_rows = list(statistics_org_page.object_list)
        statistics_org_pagination_query = statistics_base_query

    if statistics_data.get("teacher_overview"):
        statistics_teacher_page = Paginator(statistics_data["teacher_overview"], 8).get_page(
            request.GET.get(statistics_teacher_page_param)
        )
        statistics_teacher_rows = list(statistics_teacher_page.object_list)
        statistics_teacher_pagination_query = statistics_base_query

    if statistics_data.get("course_rankings"):
        statistics_course_page = Paginator(statistics_data["course_rankings"], 8).get_page(
            request.GET.get(statistics_course_page_param)
        )
        statistics_course_rows = list(statistics_course_page.object_list)
        statistics_course_pagination_query = statistics_base_query

    if statistics_data.get("group_comparison"):
        statistics_group_page = Paginator(statistics_data["group_comparison"], 8).get_page(
            request.GET.get(statistics_group_page_param)
        )
        statistics_group_rows = list(statistics_group_page.object_list)
        statistics_group_pagination_query = statistics_base_query

    if statistics_data.get("course_overview"):
        statistics_teacher_course_page = Paginator(statistics_data["course_overview"], 8).get_page(
            request.GET.get(statistics_teacher_course_page_param)
        )
        statistics_teacher_course_rows = list(statistics_teacher_course_page.object_list)
        statistics_teacher_course_pagination_query = statistics_base_query

    # ── AI summary (AJAX) ─────────────────────────────────────
    if request.GET.get("stat_ai_summary") == "1" and statistics_data:
        from apps.accounts.services.statistics_selectors import build_ai_stats_payload
        from apps.exams.public import generate_exam_statistics_summary

        role_label = (
            "superadmin"
            if capabilities["is_superadmin"]
            else (
                "org_admin"
                if capabilities["is_org_admin"]
                else ("teacher" if capabilities["is_teacher"] else "student")
            )
        )
        ai_payload = build_ai_stats_payload(role=role_label, stats=statistics_data)
        result = generate_exam_statistics_summary(
            exam_title=f"Profil Statistikası ({role_label})",
            exam_type="profile_statistics",
            stats=ai_payload,
            user_id=request.user.pk,
        )
        from django.http import JsonResponse as _JR

        return _JR(result)
    return {
        "statistics_filters": statistics_filters,
        "statistics_data": statistics_data,
        "statistics_courses": statistics_courses,
        "statistics_groups": statistics_groups,
        "statistics_organizations": statistics_organizations,
        "statistics_has_active_filters": statistics_has_active_filters,
        "statistics_unit_layout": statistics_unit_layout,
        "statistics_org_page": statistics_org_page,
        "statistics_org_rows": statistics_org_rows,
        "statistics_org_pagination_query": statistics_org_pagination_query,
        "statistics_teacher_page": statistics_teacher_page,
        "statistics_teacher_rows": statistics_teacher_rows,
        "statistics_teacher_pagination_query": statistics_teacher_pagination_query,
        "statistics_course_page": statistics_course_page,
        "statistics_course_rows": statistics_course_rows,
        "statistics_course_pagination_query": statistics_course_pagination_query,
        "statistics_group_page": statistics_group_page,
        "statistics_group_rows": statistics_group_rows,
        "statistics_group_pagination_query": statistics_group_pagination_query,
        "statistics_teacher_course_page": statistics_teacher_course_page,
        "statistics_teacher_course_rows": statistics_teacher_course_rows,
        "statistics_teacher_course_pagination_query": statistics_teacher_course_pagination_query,
    }
