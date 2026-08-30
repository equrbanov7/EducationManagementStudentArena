"""structure_views paketi — context."""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse

from ..models import OrgUnit
from ..views import _can_view_structure, _get_structure_scope
from ._shared import (
    _active_teacher_user_ids,
    _clean_sort,
    _current_academic_year_period_ids,
    _head_candidates,
    _teacher_memberships_qs,
    _unit_permission_flags,
    _visible_faculties_qs,
    _visible_kafedras_qs,
)
from .constants import (
    _SORT_OPTIONS,
    FACULTY_PAGE_SIZE,
    KAFEDRA_PAGE_SIZE,
    KAFEDRA_UNIT_TYPES,
    TEACHER_PREVIEW_LIMIT,
)


def build_organization_faculties_context(request, organization, *, form_errors=None, form_values=None, notice=""):
    scope = _get_structure_scope(request, organization)
    can_view = _can_view_structure(request, organization, scope)
    flags = _unit_permission_flags(request, organization)

    search = (request.GET.get("faculty_search") or "").strip()[:120]
    sort = _clean_sort(request.GET.get("faculty_sort"))

    faculties = (
        _visible_faculties_qs(organization, scope)
        .select_related("head")
        .annotate(
            kafedra_count=Count(
                "children",
                filter=Q(children__is_active=True, children__unit_type__in=KAFEDRA_UNIT_TYPES),
                distinct=True,
            )
        )
    )
    total_count = faculties.count()
    if search:
        faculties = faculties.filter(Q(name__icontains=search) | Q(code__icontains=search))
    faculties = faculties.order_by(*_SORT_OPTIONS[sort])

    page_obj = Paginator(faculties, FACULTY_PAGE_SIZE).get_page(request.GET.get("faculty_page"))
    kafedra_total = _visible_kafedras_qs(organization, scope).count()

    # Fakültənin müəllim sayı = onun AKTİV kafedralarına təyin olunmuş
    # müəllimlərin cəmi (bu UI-dan birbaşa fakültəyə müəllim təyinatı yoxdur —
    # bax _handle_kafedra_action.assign_teacher, həmişə kafedra tələb edir).
    # Performans: səhifədəki fakültə sayından ASILI OLMAYAN İKİ əlavə sorğu
    # (uşaq kafedra id-ləri + onların üzvlükləri) — per-fakültə sorğu YOXDUR,
    # bax test_structure_views.py-dakı sorğu-sayı kilidi.
    page_faculty_ids = [unit.id for unit in page_obj.object_list]
    kafedra_ids_by_faculty = {}
    all_kafedra_ids = []
    if page_faculty_ids:
        for kafedra_id, parent_id in OrgUnit.objects.filter(
            organization=organization,
            is_active=True,
            unit_type__in=KAFEDRA_UNIT_TYPES,
            parent_id__in=page_faculty_ids,
        ).values_list("id", "parent_id"):
            kafedra_ids_by_faculty.setdefault(parent_id, []).append(kafedra_id)
            all_kafedra_ids.append(kafedra_id)

    teachers_by_kafedra = {}
    if all_kafedra_ids:
        for membership in _teacher_memberships_qs(organization).filter(scope_unit_id__in=all_kafedra_ids):
            teachers_by_kafedra.setdefault(membership.scope_unit_id, []).append(membership)

    current_year_period_ids = _current_academic_year_period_ids(organization)
    active_teacher_ids = _active_teacher_user_ids(organization, current_year_period_ids)

    for unit in page_obj.object_list:
        members = [
            membership
            for kafedra_id in kafedra_ids_by_faculty.get(unit.id, [])
            for membership in teachers_by_kafedra.get(kafedra_id, [])
        ]
        unit.teacher_count = len(members)
        unit.active_teacher_count = sum(1 for m in members if m.user_id in active_teacher_ids)

    pagination_query = urlencode(
        {
            key: value
            for key, value in {"section": "org-faculties", "faculty_search": search, "faculty_sort": sort}.items()
            if value
        }
    )

    return {
        "organization": organization,
        "can_view": can_view,
        "faculties": page_obj,
        "faculties_page_obj": page_obj,
        "faculty_total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "kafedra_total_count": kafedra_total,
        "search_query": search,
        "sort_value": sort,
        "head_candidates": _head_candidates(organization) if flags["can_assign_members"] else [],
        "can_create": flags["can_create"] and scope.is_org_wide,
        "can_edit": flags["can_edit"],
        "can_delete": flags["can_delete"],
        "can_assign_head": flags["can_assign_members"],
        "pagination_query": pagination_query,
        "form_errors": form_errors or {},
        "form_values": form_values or {},
        "notice": notice,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


def build_organization_kafedras_context(request, organization, *, form_errors=None, form_values=None, notice=""):
    scope = _get_structure_scope(request, organization)
    can_view = _can_view_structure(request, organization, scope)
    flags = _unit_permission_flags(request, organization)

    search = (request.GET.get("kafedra_search") or "").strip()[:120]
    sort = _clean_sort(request.GET.get("kafedra_sort"))
    faculty_filter = (request.GET.get("kafedra_faculty") or "").strip()

    faculty_options = list(_visible_faculties_qs(organization, scope).only("id", "name").order_by("name"))
    valid_faculty_ids = {str(faculty.id) for faculty in faculty_options}
    if faculty_filter not in valid_faculty_ids:
        faculty_filter = ""

    kafedras = _visible_kafedras_qs(organization, scope).select_related("parent", "head")
    total_count = kafedras.count()
    if search:
        kafedras = kafedras.filter(Q(name__icontains=search) | Q(code__icontains=search))
    if faculty_filter:
        kafedras = kafedras.filter(parent_id=faculty_filter)
    kafedras = kafedras.order_by(*_SORT_OPTIONS[sort])

    page_obj = Paginator(kafedras, KAFEDRA_PAGE_SIZE).get_page(request.GET.get("kafedra_page"))

    # Səhifədəki kafedraların müəllimləri — tək sorğu, N+1 yoxdur (dəyişmir).
    # "Aktiv" / "indiyə kimi" ayrımı üçün TƏK əlavə sorğu cütü (cari tədris
    # ilinin dövr id-ləri + o dövrlərdə instruktor olan istifadəçi id-ləri) —
    # səhifədəki vahid sayından ASILI DEYİL (bax test_structure_views.py-dakı
    # sorğu-sayı kilidi). Əvvəlki `teacher_count=Count(...)` annotate-i
    # `memberships__user__is_active` yoxlamırdı — yəni deaktiv istifadəçinin
    # köhnə üzvlüyü sayğaca daxil olub, aşağıdakı siyahıdan isə (user__is_active
    # tələb edən `_teacher_memberships_qs`) YOX idi. İndi sayğac və siyahı EYNİ
    # mənbədən gəlir — uyğunsuzluq aradan qalxdı.
    page_unit_ids = [unit.id for unit in page_obj.object_list]
    teachers_by_unit = {}
    if page_unit_ids:
        for membership in _teacher_memberships_qs(organization).filter(scope_unit_id__in=page_unit_ids):
            teachers_by_unit.setdefault(membership.scope_unit_id, []).append(membership)

    current_year_period_ids = _current_academic_year_period_ids(organization)
    active_teacher_ids = _active_teacher_user_ids(organization, current_year_period_ids)

    for unit in page_obj.object_list:
        members = teachers_by_unit.get(unit.id, [])
        for membership in members:
            membership.is_active_teacher = membership.user_id in active_teacher_ids
        # Kart hündürlüyü müəllim sayından asılı olmasın deyə: kartda YALNIZ
        # ilk TEACHER_PREVIEW_LIMIT nəfər avatarı göstərilir, qalanı "+N daha"
        # çipinə düşür; tam siyahı "Ətraflı bax" modalındadır (dizayn
        # pozulması fix-i — köhnə `.collapse` blok kartı aşağı dartırdı).
        unit.teacher_members = members
        unit.teacher_members_preview = members[:TEACHER_PREVIEW_LIMIT]
        unit.teacher_members_hidden_count = max(0, len(members) - TEACHER_PREVIEW_LIMIT)
        unit.teacher_count = len(members)
        unit.active_teacher_count = sum(1 for m in members if m.is_active_teacher)

    # Təyinat modalı üçün bütün müəllim üzvlükləri (cari kafedrası etiketdə).
    teacher_options = list(_teacher_memberships_qs(organization)) if flags["can_assign_members"] else []
    unassigned_teacher_count = sum(1 for membership in teacher_options if membership.scope_unit_id is None)

    pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "section": "org-kafedras",
                "kafedra_search": search,
                "kafedra_sort": sort,
                "kafedra_faculty": faculty_filter,
            }.items()
            if value
        }
    )

    return {
        "organization": organization,
        "can_view": can_view,
        "kafedras": page_obj,
        "kafedras_page_obj": page_obj,
        "kafedra_total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "faculty_total_count": len(faculty_options),
        "search_query": search,
        "sort_value": sort,
        "faculty_filter": faculty_filter,
        "faculty_options": faculty_options,
        "teacher_options": teacher_options,
        "unassigned_teacher_count": unassigned_teacher_count,
        "head_candidates": _head_candidates(organization) if flags["can_assign_members"] else [],
        "can_create": flags["can_create"] and bool(faculty_options),
        "can_edit": flags["can_edit"],
        "can_delete": flags["can_delete"],
        "can_assign_head": flags["can_assign_members"],
        "can_assign_teachers": flags["can_assign_members"],
        "pagination_query": pagination_query,
        "form_errors": form_errors or {},
        "form_values": form_values or {},
        "notice": notice,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }
