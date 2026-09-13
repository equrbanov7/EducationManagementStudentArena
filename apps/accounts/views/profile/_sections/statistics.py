"""Profil «Statistika» bölməsi — rol-aware context qurucusu (redizayn 2026-09-12).

`build_statistics_section` ya AJAX AI-xülasə üçün `JsonResponse` (erkən-return),
ya da `statistics_*` context açarlarının lüğətini qaytarır. Açar dəsti orkestr
(`context_builder/_stage3.py`) ilə müqavilədir — DƏYİŞMİR; bölmənin öz
məzmunu `statistics_data` lüğətindədir (`profile`, `kpis`, `blocks`, `extra`).

Sahibin sözü (2026-09-12, İKT rəhbərinin ekranı): «hər profil özünə aid mənalı,
yaxşı datanı görə biləcək qədər olsun». Köhnə kod hər rola eyni 8 «göndəriş»
kartını verirdi, imtahan mərkəzi əməkdaşı isə TƏLƏBƏ qoluna düşürdü. İndi
profil rola görə seçilir (aşağıda `_resolve_profile`), rəqəmlər
`apps.accounts.services.statistics_metrics` paketindən (yalnız SQL aqreqatı,
sabit sorğu sayı) gəlir. CSV ixracı (`statistics_export.py`) köhnə
selector-larda qalır — o, başqa sahibin faylıdır.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.http import HttpResponse  # noqa: F401  (tip yoxlaması üçün caller-də istifadə olunur)

from apps.accounts.views._helpers.formatting import _query_string
from apps.accounts.views._helpers.tenant import _get_active_organization

#: Superadmin təşkilat müqayisə cədvəlinin səhifə ölçüsü.
ORG_TABLE_PAGE_SIZE = 8
#: Filtr `stat_*` parametr adları — CSV ixracı ilə EYNİ (link sorğu sətrini ötürür).
FILTER_KEYS = ("date_from", "date_to", "course", "organization")


def statistics_scope(request, organization):
    """Statistika bölməsinin (və CSV ixracının) struktur ƏHATƏSİ.

    2026-09-12 (P1-11): köhnə ümumi `get_unit_scope` HƏR aktiv üzvlüyün
    `scope_unit`-ini toplayırdı — dekanın başqa fakültənin kafedrasına müəllim
    təyinatı statistikaya həmin kafedranı da qatırdı. İndi əhatə YALNIZ
    analitika açarını daşıyan üzvlükdən çıxır, iki pillə ilə:

      1. `analytics.view_all` — ORGANIZATION rolu (rektor, prorektor, RİM,
         imtahan mərkəzi) → bütün təşkilat;
      2. əks halda `analytics.view_unit` — dekan / kafedra müdiri / tyutor /
         koordinator (UNIT + `scope_unit`) → öz alt-ağacı; HR kimi
         ORGANIZATION daşıyıcısı → bütün təşkilat.

    Heç biri yoxdursa `EMPTY_SCOPE` (fail-closed). Prorektorda YALNIZ
    `view_all` var — tək açarla getsək o, boş əhatə alardı; ona görə iki pillə.
    """
    from apps.organizations.public import get_permission_scope

    scope = get_permission_scope(request.user, organization, "analytics.view_all", request=request)
    if scope.is_org_wide:
        return scope
    return get_permission_scope(request.user, organization, "analytics.view_unit", request=request)


def _read_filters(request, *, is_superadmin: bool) -> dict:
    """GET → filtr lüğəti. Köhnə `stat_group` / `stat_content_type` QƏSDƏN oxunmur:
    yeni modeldə qrup/kontent-növü süzgəci yoxdur (rəqəmlər növ üzrə deyil,
    rol üzrə qurulur); CSV ixracı öz parametrlərini ayrıca oxuyur."""
    filters = {
        "date_from": (request.GET.get("stat_date_from") or "").strip(),
        "date_to": (request.GET.get("stat_date_to") or "").strip(),
        "course": (request.GET.get("stat_course") or "").strip() or None,
        "organization": (request.GET.get("stat_organization") or "").strip() or None,
    }
    if not is_superadmin:
        filters["organization"] = None
    return filters


def _resolve_profile(capabilities, *, organization, scope) -> str:
    """Rol → statistika profili (prioritet sırası ilə).

    * superadmin → platforma;
    * org_admin aliası (rektor, prorektor, org_admin, RİM rəhbəri, dekan,
      kafedra müdiri) → əhatəsi org-wide isə `org_admin`, alt-ağac isə
      `unit_manager`, heç biri yoxdursa boş alt-ağac (fail-closed, P1-11);
    * imtahan mərkəzi (rəhbər/əməkdaş, RİM əməkdaşı) → `exam_center`;
    * tyutor / koordinator (alt-ağac) → `unit_manager`;
    * müəllim → `teacher`;
    * analitika əhatəsi olan digər heyət (HR) → `org_admin`;
    * tələbə / adi üzv / məzun → `student` (şəxsi mənzərə);
    * əhatəsiz heyət → `restricted` (boş vəziyyət; tələbə rəqəmi GÖSTƏRİLMİR).
    """
    if capabilities["is_superadmin"]:
        return "superadmin"
    if organization is None:
        return "student" if (capabilities["is_student"] or not capabilities["is_teacher"]) else "teacher"
    if capabilities["is_org_admin"]:
        return "org_admin" if scope.is_org_wide else "unit_manager"
    if capabilities.get("is_exam_center"):
        return "exam_center"
    if capabilities.get("is_tutor") and scope.is_unit_scoped:
        return "unit_manager"
    if capabilities["is_teacher"]:
        return "teacher"
    if capabilities["is_student"] or capabilities.get("can_view_student_assignments"):
        return "student"
    if scope.is_org_wide:
        return "org_admin"
    if scope.is_unit_scoped:
        return "unit_manager"
    return "restricted"


def _compute_dashboard(request, *, capabilities, profile, organization, scope, filters):
    """Profilə görə metrik modeli (keşli) + presenter. Qaytarır: (presented, courses, orgs)."""
    from apps.accounts.services import statistics_metrics as sm
    from core.cache import get_or_set_cached_statistics

    user = request.user
    date_from = sm.parse_date(filters["date_from"])
    date_to = sm.parse_date(filters["date_to"])
    courses_options: list = []
    org_options: list = []
    presented = None
    window = None

    if profile == "superadmin":
        from apps.organizations.models import Organization

        org_options = list(
            Organization.objects.filter(is_active=True, status="active").order_by("name").values("id", "name")[:150]
        )
        allowed = {str(row["id"]) for row in org_options}
        if filters["organization"] and filters["organization"] not in allowed:
            filters["organization"] = None
        window = sm.build_window(date_from=date_from, date_to=date_to, period=None)
        metrics = get_or_set_cached_statistics(
            role="v2:superadmin",
            scope_id=filters["organization"] or "global",
            filters={**window.as_dict(), "organization": filters["organization"]},
            compute=lambda: sm.superadmin_metrics(window=window, organization_id=filters["organization"]),
        )
        presented = sm.present_superadmin(metrics)
        presented["org_comparison"] = metrics["org_comparison"]
    elif profile == "student":
        filters.update(date_from="", date_to="", course=None, organization=None)
        # Şəxsi akademik mənzərə — tarix süzgəci TƏTBİQ OLUNMUR (ECTS/ÜOMG/davamiyyət
        # semestr əsaslıdır; «semestr üzrə» bloku müqayisəni özü verir).
        metrics = get_or_set_cached_statistics(
            role="v2:student",
            scope_id=user.pk,
            filters={"_org": getattr(organization, "pk", None)},
            compute=lambda: sm.student_metrics(user, organization=organization),
        )
        presented = sm.present_student(metrics)
    elif profile == "teacher":
        from apps.courses.models import Course

        course_qs = Course.objects.filter(owner=user)
        if organization is not None:
            course_qs = course_qs.filter(organization=organization)
        courses_options = list(course_qs.order_by("title").values("id", "title")[:100])
        allowed = {str(row["id"]) for row in courses_options}
        if filters["course"] and filters["course"] not in allowed:
            filters["course"] = None
        period = sm.resolve_period(organization)
        window = sm.build_window(date_from=date_from, date_to=date_to, period=period)
        course_id = filters["course"]
        metrics = get_or_set_cached_statistics(
            role="v2:teacher",
            scope_id=user.pk,
            filters={**window.as_dict(), "course": course_id, "_org": getattr(organization, "pk", None)},
            compute=lambda: sm.teacher_metrics(
                user, organization=organization, window=window, period=period, course_id=course_id
            ),
        )
        presented = sm.present_teacher(metrics)
    elif profile == "exam_center":
        period = sm.resolve_period(organization)
        window = sm.build_window(date_from=date_from, date_to=date_to, period=period)
        metrics = get_or_set_cached_statistics(
            role="v2:exam_center",
            scope_id=organization.pk,
            filters=window.as_dict(),
            compute=lambda: sm.exam_center_metrics(organization=organization, window=window, period=period),
        )
        presented = sm.present_exam_center(metrics)
    elif profile in ("org_admin", "unit_manager"):
        from apps.organizations.models import OrgUnit

        scoped_unit_ids = None
        if profile == "unit_manager":
            # Alt-ağac id-ləri bir dəfə; əhatəsiz idarəçi BOŞ alt-ağac alır (P1-11).
            scoped_unit_ids = (
                list(
                    OrgUnit.objects.filter(organization=organization)
                    .filter(scope.unit_subtree_q())
                    .values_list("pk", flat=True)
                )
                if scope.is_unit_scoped
                else []
            )
        period = sm.resolve_period(organization)
        window = sm.build_window(date_from=date_from, date_to=date_to, period=period)
        cache_scope = f"{organization.pk}:{user.pk}" if scoped_unit_ids is not None else organization.pk
        metrics = get_or_set_cached_statistics(
            role=f"v2:{profile}",
            scope_id=cache_scope,
            filters={
                **window.as_dict(),
                "units": sorted(str(pk) for pk in scoped_unit_ids) if scoped_unit_ids is not None else None,
            },
            compute=lambda: sm.org_metrics(
                organization=organization, window=window, period=period, scoped_unit_ids=scoped_unit_ids
            ),
        )
        exam_center = None
        if profile == "org_admin" and capabilities.get("is_exam_center"):
            # RİM rəhbəri: təşkilat mənzərəsi + imtahan mərkəzi bloku.
            exam_center = get_or_set_cached_statistics(
                role="v2:exam_center",
                scope_id=organization.pk,
                filters=window.as_dict(),
                compute=lambda: sm.exam_center_metrics(organization=organization, window=window, period=period),
            )
        presented = sm.present_org(metrics, exam_center=exam_center)

    if presented is None:
        presented = {"profile": profile, "scope_label": "", "kpis": [], "blocks": [], "extra": []}
    presented["window"] = window.as_dict() if window is not None else None
    presented["has_data"] = bool(
        presented["kpis"]
        or any(block.get("bars") or block.get("rows") for block in presented["blocks"])
        or presented.get("extra")
    )
    presented["show_filters"] = profile not in ("student", "restricted")
    return presented, courses_options, org_options


def _ai_summary_response(request, *, profile, presented):
    """`?stat_ai_summary=1` — göstərilən kart/bloklardan AI xülasəsi (JSON)."""
    from django.http import JsonResponse

    from apps.exams.public import generate_exam_statistics_summary

    if not presented.get("has_data"):
        from django.utils.translation import pgettext

        # F-10 (2026-09-13): «məlumat yoxdur» 200 deyil, 404 — JS (`ai_summary.js`)
        # cavabı statusdan asılı olmayaraq `response.json()` ilə oxuyur.
        return JsonResponse({"ok": False, "error": pgettext("profile.statistics", "no_data_found")}, status=404)
    payload = {
        "role": profile,
        "scope": presented.get("scope_label") or "",
        "window": presented.get("window"),
        "kpis": [
            {"label": k["label"], "value": k["value"], "unit": k.get("unit") or "", "note": k.get("note") or ""}
            for k in presented["kpis"]
        ],
        "blocks": [
            {
                "title": block["title"],
                "items": [
                    {"label": bar["label"], "value": bar["value_label"], "note": bar.get("sub") or ""}
                    for bar in (block.get("bars") or [])
                ]
                or [
                    {"row": row["row_head"], "cells": [c.get("text", "") for c in row["cells"]]}
                    for row in (block.get("rows") or [])
                ],
            }
            for block in presented["blocks"]
        ],
    }
    result = generate_exam_statistics_summary(
        exam_title=f"Profil Statistikası ({profile})",
        exam_type="profile_statistics",
        stats=payload,
        user_id=request.user.pk,
    )
    return JsonResponse(result)


def build_statistics_section(request, *, capabilities):
    stat_org = _get_active_organization(request)
    filters = _read_filters(request, is_superadmin=capabilities["is_superadmin"])

    scope = None
    if stat_org is not None and not capabilities["is_superadmin"]:
        scope = statistics_scope(request, stat_org)
    profile = _resolve_profile(capabilities, organization=stat_org, scope=scope)

    presented, courses_options, org_options = _compute_dashboard(
        request,
        capabilities=capabilities,
        profile=profile,
        organization=stat_org,
        scope=scope,
        filters=filters,
    )

    if request.GET.get("stat_ai_summary") == "1":
        return _ai_summary_response(request, profile=profile, presented=presented)

    base_query = _query_string(
        section="statistics",
        stat_date_from=filters["date_from"],
        stat_date_to=filters["date_to"],
        stat_course=filters["course"],
        stat_organization=filters["organization"],
    )
    from apps.accounts.services.statistics_metrics.filters import filter_fields

    presented["query_string"] = base_query
    presented["filter_fields"] = filter_fields(filters, courses_options, org_options, profile)
    org_page = None
    org_rows: list = []
    org_pagination_query = ""
    if presented.get("org_comparison"):
        org_page = Paginator(presented["org_comparison"], ORG_TABLE_PAGE_SIZE).get_page(
            request.GET.get("stats_org_page")
        )
        org_rows = list(org_page.object_list)
        org_pagination_query = base_query

    return {
        "statistics_filters": filters,
        "statistics_data": presented,
        "statistics_courses": courses_options,
        "statistics_groups": [],
        "statistics_organizations": org_options,
        "statistics_has_active_filters": any(filters[key] for key in FILTER_KEYS),
        "statistics_unit_layout": profile == "unit_manager",
        "statistics_org_page": org_page,
        "statistics_org_rows": org_rows,
        "statistics_org_pagination_query": org_pagination_query,
        "statistics_teacher_page": None,
        "statistics_teacher_rows": [],
        "statistics_teacher_pagination_query": "",
        "statistics_course_page": None,
        "statistics_course_rows": [],
        "statistics_course_pagination_query": "",
        "statistics_group_page": None,
        "statistics_group_rows": [],
        "statistics_group_pagination_query": "",
        "statistics_teacher_course_page": None,
        "statistics_teacher_course_rows": [],
        "statistics_teacher_course_pagination_query": "",
    }
