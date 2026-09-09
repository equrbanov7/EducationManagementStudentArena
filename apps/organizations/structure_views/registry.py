"""Fakültələr / Kafedralar kabinet bölmələri — reyestr context-i (2026-09-08).

Sahib şikayəti: hər iki bölmə BOŞ görünürdü (əhatə səhvi — bax `context.py`
qeydi) və dizayn «AI kimi» idi. Bölmələr `ems_ui` komponentləri ilə yenidən
qurulur: KPI sırası, AVTO filtr (Bootstrap select, «Tətbiq et» yoxdur, «Sıfırla»
qalır), cədvəl, «Heyət» çekmecəsi və təyinat dialoqları:

* fakültə → dekan · dekan müavini · proqram koordinatoru;
* kafedra → kafedra müdiri · müəllim;
* hər iki növ → yarat / redaktə / arxivlə (səbəb ≥20, audit).

ƏHATƏ `unit.view` açarına görədir (`tree_scope`): dekan öz fakültəsini, müdir
öz kafedrasını görür; RİM / Tədris şöbəsi / prorektor kimi ORGANIZATION rolları
bütün siyahını alır. Yazma bayraqları `registry_flags`-dadır.

SORĞU BÜDCƏSİ səhifə ölçüsündən asılı deyil: bütün aktiv vahidlər BİR sorğu ilə
(id, path, tip) götürülür; tələbə/müəllim sayları qruplaşdırılmış TƏK sorğu
ilə gəlir və sahib vahidə path prefiksi (`OrgUnit.path` = əcdad id-ləri) ilə
Python-da paylanır. Heyət (müavin/koordinator) üzvlükləri də bir sorğudur.
"""

from __future__ import annotations

import json
from collections import defaultdict
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.translation import pgettext

from core.constants import OrgUnitType

from ..models import OrgUnit
from ..views import _can_manage_organization, _has_org_permission, _visible_units_queryset
from ._shared import (
    _active_teacher_user_ids,
    _current_academic_year_period_ids,
    _teacher_memberships_qs,
    _unit_permission_flags,
)
from .constants import KAFEDRA_UNIT_TYPES
from .registry_people import catalog_user_ids as _catalog_user_ids
from .registry_people import display_name as _display_name
from .registry_people import head_of as _head_of
from .registry_people import initials as _initials
from .registry_people import person as _person
from .registry_people import person_url as _person_url
from .registry_people import role_heads as _role_heads
from .registry_people import staff_by_root as _staff_by_root
from .tree import tree_scope

_CTX = "organizations.registry"

PAGE_SIZE = 15
TEACHER_PREVIEW = 3

DEAN_ROLE = "dean"
CHAIR_HEAD_ROLE = "chair_head"
VICE_DEAN_ROLE = "vice_dean"
COORDINATOR_ROLE = "program_coordinator"

#: Rol açarı → AZ etiket (dialoq başlıqları, çekmecə qrupları, audit mesajları).
ROLE_LABELS = {
    DEAN_ROLE: pgettext(_CTX, "Dekan"),
    CHAIR_HEAD_ROLE: pgettext(_CTX, "Kafedra müdiri"),
    VICE_DEAN_ROLE: pgettext(_CTX, "Dekan müavini"),
    COORDINATOR_ROLE: pgettext(_CTX, "Proqram koordinatoru"),
    "teacher": pgettext(_CTX, "Müəllim"),
}

_TYPE_LABELS = {
    OrgUnitType.FACULTY: pgettext(_CTX, "Fakültə"),
    OrgUnitType.CHAIR: pgettext(_CTX, "Kafedra"),
    OrgUnitType.DEPARTMENT: pgettext(_CTX, "Şöbə"),
    OrgUnitType.SPECIALTY: pgettext(_CTX, "İxtisas"),
    OrgUnitType.GROUP: pgettext(_CTX, "Qrup"),
    OrgUnitType.LAB: pgettext(_CTX, "Laboratoriya"),
    OrgUnitType.CENTER: pgettext(_CTX, "Mərkəz"),
    OrgUnitType.INSTITUTE: pgettext(_CTX, "İnstitut"),
    OrgUnitType.DEANERY: pgettext(_CTX, "Dekanlıq"),
}

SORTS = {
    "name": ("name",),
    "-name": ("-name",),
    "newest": ("-created_at", "name"),
    "oldest": ("created_at", "name"),
}


def unit_type_label(unit_type: str) -> str:
    return _TYPE_LABELS.get(unit_type, unit_type or "")


def registry_flags(request, organization) -> dict:
    """Struktur yazma bayraqları + rəhbər təyini (`unit.assign_head` VƏ YA `member.edit`)."""
    flags = _unit_permission_flags(request, organization)
    can_manage = _can_manage_organization(request.user, organization)
    flags["can_assign_head"] = (
        can_manage or flags["can_assign_members"] or _has_org_permission(request, "unit.assign_head")
    )
    return flags


# ─── Alt-ağac köməkçiləri ───────────────────────────────────────────────────


def _owner_lookup(index: dict):
    """`path` → sahib vahid id-si (ən yaxın əcdad, özü daxil) — path id-lərdən ibarətdir."""

    def owner(path):
        if not path:
            return None
        parts = path.split("/")
        for count in range(len(parts), 0, -1):
            hit = index.get("/".join(parts[:count]))
            if hit is not None:
                return hit
        return None

    return owner


def _collect(organization, roots):
    """Kök vahidlər (fakültələr və ya kafedralar) üzrə say və alt siyahılar.

    Qaytarır ``(per_root, path_by_id, owner)``:
    ``per_root[id] = {"chairs", "specialties", "groups", "students", "teachers", "specialty_list"}``.
    """
    from apps.registrar.models import StudentAcademicRecord

    owner = _owner_lookup({unit.path: unit.id for unit in roots})
    path_by_id = {}
    per = defaultdict(
        lambda: {"chairs": 0, "specialties": 0, "groups": 0, "students": 0, "teachers": 0, "specialty_list": []}
    )
    unit_rows = OrgUnit.objects.filter(organization=organization, is_active=True).values_list(
        "id", "path", "unit_type", "name"
    )
    for unit_id, path, unit_type, name in unit_rows:
        path_by_id[unit_id] = path
        root = owner(path)
        if root is None or root == unit_id:
            continue
        bucket = per[root]
        if unit_type in KAFEDRA_UNIT_TYPES:
            bucket["chairs"] += 1
        elif unit_type == OrgUnitType.SPECIALTY:
            bucket["specialties"] += 1
            bucket["specialty_list"].append({"id": str(unit_id), "name": name})
        elif unit_type == OrgUnitType.GROUP:
            bucket["groups"] += 1

    student_rows = (
        StudentAcademicRecord.objects.filter(organization=organization, is_active=True, group_id__isnull=False)
        .order_by()
        .values_list("group_id")
        .annotate(total=Count("id"))
    )
    for group_id, total in student_rows:
        root = owner(path_by_id.get(group_id))
        if root is not None:
            per[root]["students"] += total

    teacher_rows = (
        _teacher_memberships_qs(organization)
        .order_by()
        .values_list("scope_unit_id")
        .annotate(total=Count("user_id", distinct=True))
    )
    for scope_unit_id, total in teacher_rows:
        if scope_unit_id is None:
            continue
        root = owner(path_by_id.get(scope_unit_id))
        if root is not None:
            per[root]["teachers"] += total

    for bucket in per.values():
        bucket["specialty_list"].sort(key=lambda item: item["name"].lower())
    return per, path_by_id, owner


def _head_options():
    return [
        {"value": "", "label": pgettext(_CTX, "Hamısı")},
        {"value": "with", "label": pgettext(_CTX, "Rəhbəri var")},
        {"value": "without", "label": pgettext(_CTX, "Rəhbəri yoxdur")},
    ]


def _sort_options():
    return [
        {"value": "name", "label": pgettext(_CTX, "Ad (A→Z)")},
        {"value": "-name", "label": pgettext(_CTX, "Ad (Z→A)")},
        {"value": "newest", "label": pgettext(_CTX, "Ən yeni")},
        {"value": "oldest", "label": pgettext(_CTX, "Ən köhnə")},
    ]


def _apply_common_filters(queryset, *, search, head, with_head_ids=None):
    """Ad/kod axtarışı + «rəhbəri var/yox» süzgəci.

    Rəhbər süzgəci `head__isnull` ilə DEYİL, ƏVVƏLCƏDƏN hesablanmış effektiv
    rəhbər dəsti ilə tətbiq olunur (`_role_heads`): rəhbər rol üzvlüyü ilə də
    verilə bilər, FK isə boş qalır — əks halda süzgəc KPI ilə ziddiyyət yaradır.
    """
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
    if with_head_ids is None:
        return queryset
    if head == "with":
        queryset = queryset.filter(pk__in=with_head_ids)
    elif head == "without":
        queryset = queryset.exclude(pk__in=with_head_ids)
    return queryset


# ─── Ortaq qabıq ────────────────────────────────────────────────────────────


def _denied():
    return {
        "has_access": False,
        "access_denied_message": pgettext(
            _CTX, "Struktur bölmələrinə baxış üçün əhatəniz yoxdur. Rolunuza bölmə (fakültə/kafedra) təyin edilməlidir."
        ),
    }


def _base(request, organization, scope, flags, *, kind):
    slug = organization.slug
    prefix = "fc_" if kind == "faculty" else "kf_"
    return {
        "has_access": True,
        "kind": kind,
        "prefix": prefix,
        "is_org_wide": scope.is_org_wide,
        **flags,
        "action_url": reverse("organizations:structure_unit_action", args=[slug]),
        "candidates_url": reverse("organizations:structure_role_candidates", args=[slug]),
        "form_data": {"data-tof-form": "1"},
        "unit_hidden": [
            {"name": "action", "value": "save_unit", "keep": True},
            {"name": "kind", "value": kind, "keep": True},
            {"name": "id", "value": ""},
        ],
        "head_hidden": [
            {"name": "action", "value": "assign_head", "keep": True},
            {"name": "id", "value": ""},
        ],
        "role_hidden": [
            {"name": "action", "value": "add_role", "keep": True},
            {"name": "id", "value": ""},
            {"name": "role", "value": ""},
        ],
        "teacher_hidden": [
            {"name": "action", "value": "add_teacher", "keep": True},
            {"name": "id", "value": ""},
        ],
        "archive_hidden": [
            {"name": "action", "value": "archive_unit", "keep": True},
            {"name": "id", "value": ""},
        ],
        "sort_options": _sort_options(),
        "head_options": _head_options(),
        "role_labels": ROLE_LABELS,
    }


def _visible_faculties(organization, scope):
    return _visible_units_queryset(organization, scope).filter(unit_type=OrgUnitType.FACULTY)


def _faculty_options(organization, scope):
    return [
        {"value": str(unit.id), "label": unit.name}
        for unit in _visible_faculties(organization, scope).only("id", "name").order_by("name")
    ]


# ─── Fakültələr ─────────────────────────────────────────────────────────────


def build_faculties_section(request, organization) -> dict:
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _denied()
    flags = registry_flags(request, organization)
    section = _base(request, organization, scope, flags, kind="faculty")
    slug = organization.slug

    search = (request.GET.get("fc_q") or "").strip()[:120]
    head = (request.GET.get("fc_head") or "").strip()
    sort = (request.GET.get("fc_sort") or "").strip()
    sort = sort if sort in SORTS else "name"

    base_qs = _visible_faculties(organization, scope).select_related("head")
    all_faculties = list(base_qs.order_by("name"))
    total_count = len(all_faculties)
    per, _paths, owner = _collect(organization, all_faculties)
    staff = _staff_by_root(organization, owner, (VICE_DEAN_ROLE, COORDINATOR_ROLE))
    role_heads = _role_heads(organization, all_faculties, DEAN_ROLE)
    with_head_ids = {unit.id for unit in all_faculties if unit.head_id or unit.id in role_heads}
    linkable_heads = _catalog_user_ids(
        organization,
        [unit.head_id for unit in all_faculties] + [m.user_id for m in role_heads.values()],
    )

    queryset = _apply_common_filters(base_qs, search=search, head=head, with_head_ids=with_head_ids).order_by(
        *SORTS[sort]
    )
    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("fc_page"))

    rows = []
    for unit in page_obj.object_list:
        bucket = per[unit.id]
        people = staff.get(unit.id, {})
        head_name, head_user_id = _head_of(unit, role_heads)
        rows.append(
            {
                "id": str(unit.id),
                "name": unit.name,
                "code": unit.code or "",
                "head_id": str(unit.head_id) if unit.head_id else "",
                "head_user_id": str(head_user_id or ""),
                "head_url": _person_url(head_user_id if head_user_id in linkable_heads else None),
                "head_name": head_name,
                "head_initials": _initials(head_name) if head_name else "",
                "vice_deans": [_person(m, root_id=unit.id) for m in people.get(VICE_DEAN_ROLE, [])],
                "coordinators": [_person(m, root_id=unit.id) for m in people.get(COORDINATOR_ROLE, [])],
                "chairs": bucket["chairs"],
                "specialties": bucket["specialties"],
                "groups": bucket["groups"],
                "teachers": bucket["teachers"],
                "students": bucket["students"],
                "specialties_json": json.dumps(bucket["specialty_list"], ensure_ascii=False),
                "staff_url": reverse("organizations:structure_unit_staff", args=[slug, unit.id]),
                "kafedras_url": f"{reverse('accounts:profile')}?section=org-kafedras&kf_faculty={unit.id}",
            }
        )

    # ⚠️ BİRİNCİ sütun sətir başlığıdır (`th scope="row"`), SONUNCU isə əməllər
    # xanasıdır. 2026-09-09-a qədər hər ikisinin başlığı buraxılmışdı — nəticədə
    # başlıqlar bir xana SOLA sürüşürdü («Fakültə» sütununun üstündə «Dekan»
    # yazırdı; sahib şikayəti).
    columns = [
        {"key": "faculty", "label": pgettext(_CTX, "Fakültə")},
        {"key": "head", "label": pgettext(_CTX, "Dekan")},
        {"key": "staff", "label": pgettext(_CTX, "Müavinlər · Koordinatorlar")},
        {"key": "chairs", "label": pgettext(_CTX, "Kafedra"), "align": "num"},
        {"key": "teachers", "label": pgettext(_CTX, "Müəllim"), "align": "num"},
        {"key": "students", "label": pgettext(_CTX, "Tələbə"), "align": "num"},
        {"key": "actions", "label": pgettext(_CTX, "Əməllər"), "align": "end"},
    ]
    cell_dir = "accounts/profile/sections/org_units/"
    table_rows = [
        {
            "row_head": row["name"],
            "head_include": f"{cell_dir}_cell_unit.html",
            "cells": [
                {"include": f"{cell_dir}_cell_head.html"},
                {"include": f"{cell_dir}_cell_people.html"},
                {"text": row["chairs"], "num": True},
                {"text": row["teachers"], "num": True},
                {"text": row["students"], "num": True},
            ],
            "actions_include": f"{cell_dir}_faculty_row_actions.html",
            "data": row,
        }
        for row in rows
    ]

    no_head = sum(1 for unit in all_faculties if unit.id not in with_head_ids)
    kpi_tiles = [
        {"label": pgettext(_CTX, "Fakültə"), "value": total_count, "tone": "primary"},
        {"label": pgettext(_CTX, "Kafedra"), "value": sum(per[u.id]["chairs"] for u in all_faculties)},
        {
            "label": pgettext(_CTX, "Dekansız"),
            "value": no_head,
            "tone": "accent-warning" if no_head else "accent-success",
            "note": pgettext(_CTX, "rəhbər təyin edilməyib") if no_head else pgettext(_CTX, "hamısında dekan var"),
        },
        {"label": pgettext(_CTX, "Müəllim"), "value": sum(per[u.id]["teachers"] for u in all_faculties)},
        {"label": pgettext(_CTX, "Tələbə"), "value": sum(per[u.id]["students"] for u in all_faculties)},
    ]

    filter_fields = [
        {
            "name": "fc_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": search,
            "wide": True,
            "placeholder": pgettext(_CTX, "Fakültə adı və ya kodu"),
        },
        {
            "name": "fc_head",
            "label": pgettext(_CTX, "Dekan"),
            "kind": "select",
            "options": _head_options(),
            "value": head,
        },
        {
            "name": "fc_sort",
            "label": pgettext(_CTX, "Sıralama"),
            "kind": "select",
            "options": _sort_options(),
            "value": sort,
            "default": "name",
        },
    ]
    base_params = {
        "section": "org-faculties",
        "fc_q": search,
        "fc_head": head,
        "fc_sort": sort if sort != "name" else "",
    }

    section.update(
        {
            "rows": rows,
            "table_rows": table_rows,
            "columns": columns,
            "table_state": "ready" if rows else "empty",
            "page_obj": page_obj,
            "pagination_query": urlencode({k: v for k, v in base_params.items() if v}),
            "total_count": total_count,
            "filtered_count": page_obj.paginator.count,
            "kpi_tiles": kpi_tiles,
            "filter_fields": filter_fields,
            "filter_count_label": pgettext(_CTX, "Nəticə: %(n)d fakültə") % {"n": page_obj.paginator.count},
            "state_title": (
                pgettext(_CTX, "Filtrə uyğun fakültə yoxdur")
                if (search or head)
                else pgettext(_CTX, "Hələ fakültə yaradılmayıb")
            ),
            "state_body": (
                pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.")
                if (search or head)
                else pgettext(_CTX, "«Yeni fakültə» ilə ilk fakültəni yaradın; kafedralar ona bağlanacaq.")
            ),
            "subtitle": pgettext(
                _CTX,
                "Fakültələr, dekan və dekanlıq heyəti. Hər sətirdə «Heyət» çekmecəsi tam siyahını açır; "
                "dekan, müavin və koordinator təyinatı buradan aparılır.",
            ),
        }
    )
    return section


# ─── Kafedralar ─────────────────────────────────────────────────────────────


def build_kafedras_section(request, organization) -> dict:
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _denied()
    flags = registry_flags(request, organization)
    section = _base(request, organization, scope, flags, kind="kafedra")
    slug = organization.slug

    search = (request.GET.get("kf_q") or "").strip()[:120]
    faculty = (request.GET.get("kf_faculty") or "").strip()
    head = (request.GET.get("kf_head") or "").strip()
    sort = (request.GET.get("kf_sort") or "").strip()
    sort = sort if sort in SORTS else "name"

    base_qs = (
        _visible_units_queryset(organization, scope)
        .filter(unit_type__in=KAFEDRA_UNIT_TYPES)
        .select_related("head", "parent")
    )
    all_chairs = list(base_qs.order_by("name"))
    total_count = len(all_chairs)
    per, _paths, owner = _collect(organization, all_chairs)
    role_heads = _role_heads(organization, all_chairs, CHAIR_HEAD_ROLE)
    with_head_ids = {unit.id for unit in all_chairs if unit.head_id or unit.id in role_heads}
    linkable_heads = _catalog_user_ids(
        organization,
        [unit.head_id for unit in all_chairs] + [m.user_id for m in role_heads.values()],
    )

    queryset = _apply_common_filters(base_qs, search=search, head=head, with_head_ids=with_head_ids)
    if faculty:
        queryset = queryset.filter(parent_id=faculty)
    queryset = queryset.order_by(*SORTS[sort])
    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("kf_page"))

    page_ids = [unit.id for unit in page_obj.object_list]
    teachers_by_chair = defaultdict(list)
    if page_ids:
        for membership in _teacher_memberships_qs(organization).filter(scope_unit_id__in=page_ids):
            teachers_by_chair[membership.scope_unit_id].append(membership)

    # Cari tədris ilində dərs deyən («aktiv») müəllimlər və onların açılış sayı —
    # kafedra üzrə. İxtisas/qrup/tələbə sayı QƏSDƏN göstərilmir: bir çox
    # tenantda ixtisas və qruplar kafedranın deyil, fakültənin altındadır və o
    # sütunlar həmişə «0» görünürdü (QA klonunda müşahidə, 2026-09-08).
    period_ids = _current_academic_year_period_ids(organization)
    active_ids = _active_teacher_user_ids(organization, period_ids)
    offerings_by_user = {}
    if period_ids:
        from apps.registrar.models import CourseOffering

        offerings_by_user = dict(
            CourseOffering.objects.filter(
                organization=organization, is_active=True, period_id__in=period_ids, instructor_id__isnull=False
            )
            .order_by()
            .values_list("instructor_id")
            .annotate(total=Count("id"))
        )
    chair_of_user = defaultdict(set)
    for user_id, scope_unit_id in (
        _teacher_memberships_qs(organization).order_by().values_list("user_id", "scope_unit_id")
    ):
        if scope_unit_id is not None:
            chair_of_user[user_id].add(scope_unit_id)
    active_by_chair = defaultdict(int)
    offerings_by_chair = defaultdict(int)
    for user_id, chairs in chair_of_user.items():
        for chair_id in chairs:
            if user_id in active_ids:
                active_by_chair[chair_id] += 1
            offerings_by_chair[chair_id] += offerings_by_user.get(user_id, 0)

    rows = []
    for unit in page_obj.object_list:
        bucket = per[unit.id]
        teachers = teachers_by_chair.get(unit.id, [])
        seen, preview = set(), []
        for membership in teachers:
            if membership.user_id in seen:
                continue
            seen.add(membership.user_id)
            preview.append(
                {"name": _display_name(membership.user), "initials": _initials(_display_name(membership.user))}
            )
        head_name, head_user_id = _head_of(unit, role_heads)
        rows.append(
            {
                "id": str(unit.id),
                "name": unit.name,
                "code": unit.code or "",
                "unit_type": unit.unit_type,
                "type_label": unit_type_label(unit.unit_type),
                "faculty_id": str(unit.parent_id) if unit.parent_id else "",
                "faculty_name": unit.parent.name if unit.parent_id else "",
                "head_id": str(unit.head_id) if unit.head_id else "",
                "head_user_id": str(head_user_id or ""),
                "head_url": _person_url(head_user_id if head_user_id in linkable_heads else None),
                "head_name": head_name,
                "head_initials": _initials(head_name) if head_name else "",
                "teacher_preview": preview[:TEACHER_PREVIEW],
                "teacher_more": max(0, len(preview) - TEACHER_PREVIEW),
                "teachers": len(preview),
                "active_teachers": active_by_chair.get(unit.id, 0),
                "offerings": offerings_by_chair.get(unit.id, 0),
                "specialties": bucket["specialties"],
                "groups": bucket["groups"],
                "students": bucket["students"],
                "specialties_json": json.dumps(bucket["specialty_list"], ensure_ascii=False),
                "staff_url": reverse("organizations:structure_unit_staff", args=[slug, unit.id]),
            }
        )

    # Bax fakültə cədvəlindəki qeyd: birinci sütun sətir başlığı, sonuncu isə
    # əməllər xanasıdır — hər ikisinin başlığı OLMALIDIR, yoxsa başlıqlar sürüşür.
    columns = [
        {"key": "kafedra", "label": pgettext(_CTX, "Kafedra")},
        {"key": "faculty", "label": pgettext(_CTX, "Fakültə")},
        {"key": "head", "label": pgettext(_CTX, "Kafedra müdiri")},
        {"key": "teachers", "label": pgettext(_CTX, "Müəllimlər")},
        {"key": "active", "label": pgettext(_CTX, "Bu il aktiv"), "align": "num"},
        {"key": "offerings", "label": pgettext(_CTX, "Açılış (cari il)"), "align": "num"},
        {"key": "actions", "label": pgettext(_CTX, "Əməllər"), "align": "end"},
    ]
    cell_dir = "accounts/profile/sections/org_units/"
    table_rows = [
        {
            "row_head": row["name"],
            "head_include": f"{cell_dir}_cell_unit.html",
            "cells": [
                {"text": row["faculty_name"] or "—", "muted": not row["faculty_name"]},
                {"include": f"{cell_dir}_cell_head.html"},
                {"include": f"{cell_dir}_cell_teachers.html"},
                {"text": row["active_teachers"], "num": True},
                {"text": row["offerings"], "num": True},
            ],
            "actions_include": f"{cell_dir}_kafedra_row_actions.html",
            "data": row,
        }
        for row in rows
    ]

    no_head = sum(1 for unit in all_chairs if unit.id not in with_head_ids)
    kpi_tiles = [
        {"label": pgettext(_CTX, "Kafedra"), "value": total_count, "tone": "primary"},
        {
            "label": pgettext(_CTX, "Müdirsiz"),
            "value": no_head,
            "tone": "accent-warning" if no_head else "accent-success",
            "note": pgettext(_CTX, "müdir təyin edilməyib") if no_head else pgettext(_CTX, "hamısında müdir var"),
        },
        {"label": pgettext(_CTX, "Müəllim"), "value": sum(per[u.id]["teachers"] for u in all_chairs)},
        {
            "label": pgettext(_CTX, "Bu il aktiv"),
            "value": sum(active_by_chair.get(u.id, 0) for u in all_chairs),
            "note": pgettext(_CTX, "cari tədris ilində dərs deyən"),
        },
        {
            "label": pgettext(_CTX, "Açılış"),
            "value": sum(offerings_by_chair.get(u.id, 0) for u in all_chairs),
            "note": pgettext(_CTX, "cari tədris ili"),
        },
    ]

    faculty_options = _faculty_options(organization, scope)
    filter_fields = [
        {
            "name": "kf_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": search,
            "wide": True,
            "placeholder": pgettext(_CTX, "Kafedra adı və ya kodu"),
        },
        {
            "name": "kf_faculty",
            "label": pgettext(_CTX, "Fakültə"),
            "kind": "select",
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün fakültələr")}] + faculty_options,
            "value": faculty,
            "searchable": True,
        },
        {
            "name": "kf_head",
            "label": pgettext(_CTX, "Müdir"),
            "kind": "select",
            "options": _head_options(),
            "value": head,
        },
        {
            "name": "kf_sort",
            "label": pgettext(_CTX, "Sıralama"),
            "kind": "select",
            "options": _sort_options(),
            "value": sort,
            "default": "name",
        },
    ]
    base_params = {
        "section": "org-kafedras",
        "kf_q": search,
        "kf_faculty": faculty,
        "kf_head": head,
        "kf_sort": sort if sort != "name" else "",
    }
    filtered = bool(search or faculty or head)

    section.update(
        {
            "rows": rows,
            "table_rows": table_rows,
            "columns": columns,
            "table_state": "ready" if rows else "empty",
            "page_obj": page_obj,
            "pagination_query": urlencode({k: v for k, v in base_params.items() if v}),
            "total_count": total_count,
            "filtered_count": page_obj.paginator.count,
            "kpi_tiles": kpi_tiles,
            "filter_fields": filter_fields,
            "filter_count_label": pgettext(_CTX, "Nəticə: %(n)d kafedra") % {"n": page_obj.paginator.count},
            "faculty_options": faculty_options,
            "default_faculty": faculty if any(o["value"] == faculty for o in faculty_options) else "",
            "state_title": (
                pgettext(_CTX, "Filtrə uyğun kafedra yoxdur")
                if filtered
                else pgettext(_CTX, "Hələ kafedra yaradılmayıb")
            ),
            "state_body": (
                pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.")
                if filtered
                else pgettext(_CTX, "«Yeni kafedra» ilə ilk kafedranı yaradın və fakültəyə bağlayın.")
            ),
            "subtitle": pgettext(
                _CTX,
                "Kafedralar, müdirlər və müəllim heyəti. «Heyət» çekmecəsi tam siyahını açır; "
                "müdir və müəllim təyinatı buradan aparılır.",
            ),
        }
    )
    return section


__all__ = [
    "build_faculties_section",
    "build_kafedras_section",
    "registry_flags",
    "unit_type_label",
    "ROLE_LABELS",
    "DEAN_ROLE",
    "CHAIR_HEAD_ROLE",
    "VICE_DEAN_ROLE",
    "COORDINATOR_ROLE",
    "PAGE_SIZE",
]
