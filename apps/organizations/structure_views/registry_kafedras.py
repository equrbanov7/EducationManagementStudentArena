"""Kafedralar kabinet bölməsi — ``build_kafedras_section`` (reyestr context-i).

``registry.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21); ``registry.py``
funksiyanı yenidən ixrac edir. Əhatə, sorğu büdcəsi və dizayn qeydləri üçün
bax ``registry.py`` başlığı.
"""

from __future__ import annotations

import json
from collections import defaultdict
from urllib.parse import urlencode

from django.apps import apps as django_apps
from django.core.paginator import Paginator
from django.db.models import Count
from django.urls import reverse
from django.utils.translation import pgettext

from ..views import _visible_units_queryset
from ._shared import (
    _active_teacher_user_ids,
    _current_academic_year_period_ids,
    _teacher_memberships_qs,
)
from .constants import KAFEDRA_UNIT_TYPES
from .registry_base import (
    CHAIR_HEAD_ROLE,
    PAGE_SIZE,
    SORTS,
    TEACHER_PREVIEW,
    _apply_common_filters,
    _base,
    _collect,
    _denied,
    _faculty_options,
    _head_options,
    _sort_options,
    registry_flags,
    unit_type_label,
)
from .registry_people import catalog_user_ids as _catalog_user_ids
from .registry_people import display_name as _display_name
from .registry_people import head_of as _head_of
from .registry_people import initials as _initials
from .registry_people import person_url as _person_url
from .registry_people import role_heads as _role_heads
from .tree import tree_scope

# i18n skaneri kontekst sabitini MODUL daxilində axtarır — yerli təyin.
_CTX = "organizations.registry"


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
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")

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
