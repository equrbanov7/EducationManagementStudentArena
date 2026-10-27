"""teacher exams paketi — «Tapşırıq təyin olunmuşlar» səhifəsi (sahib 2026-10-27).

İmtahanı verə bilən hər kəs (giriş siyasəti ilə EYNİ çoxluq — ``services/exam_assignees.py``): qrup çipləri
(qrup üzrə say), süzgəclər (qrup, mənbə, cəhd statusu), hərf-dözümlü axtarış, sıralama, səhifələmə.
Redaktə hüququ olan (``exam.edit`` + müəllif / mərkəz) qrup / tələbə əlavə edir, çıxarır, istisna edir
(``assignee_edit.py``); qalanlar yalnız baxır.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from apps.exams.services import exam_assignees as _assignees
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.student_pins import exam_requires_student_pins
from apps.exams.views.shared.breadcrumbs import exam_breadcrumbs
from apps.exams.views.shared.tenant import get_teacher_exam_or_404
from core.permissions import request_has_permission

from . import unit_assignment as _units
from ._shared import (
    _ensure_exam_owner_or_overseer,
    _organization_selection_redirect,
    _resolve_profile_navigation,
    _resolve_required_organization,
)

PAGE_SIZE = 50
_CTX = "exams.assignees"


def can_edit_assignees(request, exam) -> bool:
    """Sehrbazın redaktə qapısı ilə eyni: ``exam.edit`` + müəllif / superadmin / mərkəz (midterm-final)."""
    if not request_has_permission(request, "exam.edit"):
        return False
    try:
        _ensure_exam_owner_or_overseer(request, exam)
    except PermissionDenied:
        return False
    return True


def _filters(request) -> dict:
    get = request.GET
    sort_by = (get.get("sort_by") or "").strip()
    sort_dir = (get.get("sort_dir") or "").strip()
    order = (get.get("order") or "").strip()
    if order:  # «Sıralama» seçicisi: ``name_asc`` → sort_by=name, sort_dir=asc (sütun başlığı ilə eyni)
        sort_by, _, sort_dir = order.rpartition("_")
    return {
        "q": (get.get("q") or "").strip()[:120],
        "group": (get.get("group") or "").strip()[:150],
        "source": (get.get("source") or "").strip() if get.get("source") in _assignees.SOURCES else "",
        "status": (get.get("status") or "").strip() if get.get("status") in _assignees.STATUSES else "",
        "sort_by": sort_by if sort_by in _assignees.SORT_KEYS else "",
        "sort_dir": sort_dir if sort_dir in ("asc", "desc") else "",
    }


def _query(filters, nav_query, *, drop=()) -> str:
    params = [(key, value) for key, value in filters.items() if value and key not in drop]
    query = urlencode(params)
    if nav_query:
        query = f"{query}&{nav_query}" if query else nav_query
    return query


def _unit_rows(request, organization, exam, can_edit) -> list:
    units = list(exam.allowed_units.select_related("parent").order_by("name"))
    removable = set()
    if can_edit and units:
        removable = set(
            _units.exam_unit_candidates(request, organization, permission="exam.edit")
            .filter(pk__in=[unit.pk for unit in units])
            .values_list("pk", flat=True)
        )
    return [
        {"id": str(unit.pk), "label": _units.unit_display_label(unit), "removable": unit.pk in removable}
        for unit in units
    ]


def _order_choices():
    return [
        ("", pgettext(_CTX, "Ad (A → Z)")),
        ("name_desc", pgettext(_CTX, "Ad (Z → A)")),
        ("group_asc", pgettext(_CTX, "Qrup")),
        ("code_asc", pgettext(_CTX, "Tələbə kodu")),
        ("status_asc", pgettext(_CTX, "Cəhd statusu")),
    ]


def _current_order(filters) -> str:
    if (
        not filters["sort_by"]
        or not filters["sort_dir"]
        or filters["sort_by"] == "name"
        and filters["sort_dir"] == "asc"
    ):
        return ""
    return f"{filters['sort_by']}_{filters['sort_dir']}"


def _source_choices():
    return [
        ("", pgettext(_CTX, "Bütün mənbələr")),
        (_assignees.SOURCE_GROUP, pgettext(_CTX, "Qrupla")),
        (_assignees.SOURCE_INDIVIDUAL, pgettext(_CTX, "Fərdi")),
        (_assignees.SOURCE_COURSE, pgettext(_CTX, "Kursla")),
    ]


def _status_choices():
    return [
        ("", pgettext(_CTX, "Bütün statuslar")),
        (_assignees.STATUS_NOT_STARTED, pgettext(_CTX, "Başlamayıb")),
        (_assignees.STATUS_IN_PROGRESS, pgettext(_CTX, "Davam edir")),
        (_assignees.STATUS_FINISHED, pgettext(_CTX, "Bitib")),
        (_assignees.STATUS_EXCLUDED, pgettext(_CTX, "İstisna edilib")),
    ]


@login_required
@require_GET
def teacher_exam_assignees(request, slug):
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    can_edit = can_edit_assignees(request, exam)
    _, _, nav_query = _resolve_profile_navigation(request, default_section="my-exams")
    filters = _filters(request)

    rows = _assignees.build_roster(exam)
    stats = _assignees.roster_stats(rows)
    summary = _assignees.group_summary(rows)
    filtered = _assignees.filter_rows(
        rows, query=filters["q"], group=filters["group"], source=filters["source"], status=filters["status"]
    )
    if filters["sort_by"] and filters["sort_dir"]:
        filtered = _assignees.sort_rows(filtered, filters["sort_by"], filters["sort_dir"])
    page_obj = Paginator(filtered, PAGE_SIZE).get_page(request.GET.get("page"))
    _assignees.attach_scores(exam, page_obj.object_list)

    detail_url = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
    if nav_query:
        detail_url = f"{detail_url}?{nav_query}"
    title = pgettext(_CTX, "Tapşırıq təyin olunmuşlar")
    return render(
        request,
        "exams/teacher/teacher_exam_assignees.html",
        {
            "exam": exam,
            "page_title": title,
            "exam_crumbs": exam_breadcrumbs(request, exam, current=title, navigation_query=nav_query),
            "detail_url": detail_url,
            "back_label": pgettext("exams.template.teacher_exam_detail", "action_back"),
            "can_edit": can_edit,
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "row_offset": page_obj.start_index() - 1 if page_obj.paginator.count else 0,
            "filtered_count": len(filtered),
            "stats": stats,
            "group_summary": summary,
            "filters": filters,
            "has_filters": any(filters[key] for key in ("q", "group", "source", "status")),
            "source_choices": _source_choices(),
            "status_choices": _status_choices(),
            "order_choices": _order_choices(),
            "current_order": _current_order(filters),
            "pagination_query": _query(filters, nav_query),
            "sort_base_query": _query(filters, nav_query, drop=("sort_by", "sort_dir")),
            "chip_base_query": _query(filters, nav_query, drop=("group",)),
            "sort_by": filters["sort_by"],
            "sort_dir": filters["sort_dir"],
            "nav_query": nav_query,
            "assigned_units": _unit_rows(request, organization, exam, can_edit),
            "requires_pins": exam_requires_student_pins(exam),
            "update_url": reverse("exams:teacher_exam_assignees_update", kwargs={"slug": exam.slug}),
            "group_search_url": f"{reverse('exams:group_search')}?kind=units",
            "user_search_url": reverse("exams:user_search"),
        },
    )


__all__ = ["can_edit_assignees", "teacher_exam_assignees"]
