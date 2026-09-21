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

MODUL BÖLGÜSÜ (2026-09-21, modul-ölçü qapısı): ortaq sabitlər/köməkçilər
``registry_base.py``-da, kafedralar bölməsi ``registry_kafedras.py``-dadır;
bu modul fakültələr bölməsini saxlayır və bütün ictimai adları yenidən ixrac
edir (``from .registry import …`` yolları dəyişmir).
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from .registry_base import (  # noqa: F401 — yenidən ixrac
    _TYPE_LABELS,
    CHAIR_HEAD_ROLE,
    COORDINATOR_ROLE,
    DEAN_ROLE,
    PAGE_SIZE,
    ROLE_LABELS,
    SORTS,
    TEACHER_PREVIEW,
    VICE_DEAN_ROLE,
    _apply_common_filters,
    _base,
    _collect,
    _denied,
    _faculty_options,
    _head_options,
    _owner_lookup,
    _sort_options,
    _visible_faculties,
    registry_flags,
    unit_type_label,
)
from .registry_kafedras import build_kafedras_section  # noqa: F401 — yenidən ixrac
from .registry_people import catalog_user_ids as _catalog_user_ids
from .registry_people import display_name as _display_name  # noqa: F401 — yenidən ixrac (members.py)
from .registry_people import head_of as _head_of
from .registry_people import initials as _initials
from .registry_people import person as _person
from .registry_people import person_url as _person_url
from .registry_people import role_heads as _role_heads
from .registry_people import staff_by_root as _staff_by_root
from .tree import tree_scope

# i18n skaneri kontekst sabitini MODUL daxilində axtarır — yerli təyin.
_CTX = "organizations.registry"


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
