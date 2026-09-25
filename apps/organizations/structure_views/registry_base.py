"""Fakültələr / Kafedralar reyestri — ortaq sabitlər, etiketlər və köməkçilər.

``registry.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21): rol/tip etiketləri,
``registry_flags``, alt-ağac sayğacları (``_collect``), filtr seçiciləri və
bölmə qabığı (``_base``). ``registry.py`` (fakültələr) və ``registry_kafedras.py``
(kafedralar) buradan istifadə edir; ictimai adlar ``registry.py``-dan yenidən
ixrac olunur.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Count
from django.urls import reverse
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.search_text import tolerant_q

from ..models import OrgUnit
from ..views import _can_manage_organization, _has_org_permission, _visible_units_queryset
from ._shared import _teacher_memberships_qs, _unit_permission_flags
from .constants import KAFEDRA_UNIT_TYPES

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
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
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
    search_q = tolerant_q(search, ("name",), compact_fields=("code",))
    if search_q is not None:
        queryset = queryset.filter(search_q)
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
