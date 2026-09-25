"""Fakültələr / Kafedralar reyestri — «Heyət» çekmecəsi və namizəd axtarışı (GET, JSON).

``structure_registry_actions.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21):
``structure_unit_staff`` və ``structure_role_candidates``; orijinal modul onları
yenidən ixrac edir (``urls.py`` dəyişmir).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.constants import OrgUnitType
from core.search_text import tolerant_q
from core.staff_position import visible_role_label

from .models import Membership, Organization, OrgUnit
from .structure_registry_helpers import (
    CANDIDATE_MAX_PAGE_SIZE,
    CANDIDATE_PAGE_SIZE,
    _display_name,
    _error,
    _forbidden,
    _visible_unit,
)
from .structure_views._shared import (
    _teacher_memberships_qs,
    head_candidate_memberships,
    head_candidate_rows,
)
from .structure_views.constants import KAFEDRA_UNIT_TYPES, TEACHER_ROLE_NAMES
from .structure_views.registry import COORDINATOR_ROLE, ROLE_LABELS, VICE_DEAN_ROLE, registry_flags, unit_type_label
from .structure_views.tree import tree_scope

# i18n skaneri kontekst sabitini MODUL daxilində axtarır — yerli təyin.
_CTX = "organizations.registry"


# ─── «Heyət» çekmecəsi ───────────────────────────────────────────────────────


def _member_row(membership, *, unit):
    user = membership.user
    scope_unit = membership.scope_unit
    return {
        "membership_id": str(membership.id),
        "user_id": str(user.id),
        "name": _display_name(user),
        "username": user.username,
        "role": membership.role.name,
        "role_label": ROLE_LABELS.get(membership.role.name)
        or visible_role_label(membership.role.name, membership.role.display_name),
        "scope": scope_unit.name if scope_unit is not None and scope_unit.id != unit.id else "",
        "profile_url": reverse("accounts:public_profile", kwargs={"username": user.username}),
    }


@login_required
@require_GET
def structure_unit_staff(request, slug, unit_id):
    """Vahidin rəhbəri, rol qrupları və alt bölmələri — «Heyət» çekmecəsi (JSON)."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _forbidden(pgettext(_CTX, "Struktur əhatəniz yoxdur."))
    unit = _visible_unit(organization, scope, unit_id)
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")
    flags = registry_flags(request, organization)
    is_faculty = unit.unit_type == OrgUnitType.FACULTY

    subtree = Q(scope_unit_id=unit.id) | Q(scope_unit__path__startswith=f"{unit.path}/")
    role_names = (
        (VICE_DEAN_ROLE, COORDINATOR_ROLE, *TEACHER_ROLE_NAMES)
        if is_faculty
        else (COORDINATOR_ROLE, *TEACHER_ROLE_NAMES)
    )
    memberships = list(
        Membership.objects.filter(
            organization=organization, is_active=True, user__is_active=True, role__name__in=role_names
        )
        .filter(subtree)
        .select_related("user", "role", "scope_unit")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    groups = []
    order = [VICE_DEAN_ROLE, COORDINATOR_ROLE, "teacher"] if is_faculty else ["teacher", COORDINATOR_ROLE]
    for key in order:
        if key == "teacher":
            rows = [m for m in memberships if m.role.name in TEACHER_ROLE_NAMES]
            # Fakültədə müəllimlər KAFEDRA üzrədir — çekmecədə kafedra adı görünür.
            label = pgettext(_CTX, "Müəllimlər")
        else:
            rows = [m for m in memberships if m.role.name == key]
            label = ROLE_LABELS.get(key, key)
        groups.append(
            {
                "key": key,
                "label": label,
                "removable": flags["can_assign_members"],
                "members": [_member_row(m, unit=unit) for m in rows],
            }
        )

    child_types = KAFEDRA_UNIT_TYPES if is_faculty else (OrgUnitType.SPECIALTY,)
    children_qs = (
        OrgUnit.objects.filter(organization=organization, is_active=True, parent_id=unit.id, unit_type__in=child_types)
        .select_related("head")
        .order_by("name")
    )
    children = [
        {
            "id": str(child.id),
            "name": child.name,
            "code": child.code or "",
            "type_label": unit_type_label(child.unit_type),
            "head_name": _display_name(child.head) if child.head_id else "",
        }
        for child in children_qs
    ]
    return JsonResponse(
        {
            "ok": True,
            "unit": {
                "id": str(unit.id),
                "name": unit.name,
                "code": unit.code or "",
                "type": unit.unit_type,
                "type_label": unit_type_label(unit.unit_type),
                "parent_name": unit.parent.name if unit.parent_id else "",
                "head": (
                    {
                        "user_id": str(unit.head_id),
                        "name": _display_name(unit.head),
                        "username": unit.head.username,
                        "profile_url": reverse("accounts:public_profile", kwargs={"username": unit.head.username}),
                    }
                    if unit.head_id
                    else None
                ),
                "head_label": pgettext(_CTX, "Dekan") if is_faculty else pgettext(_CTX, "Kafedra müdiri"),
            },
            "groups": groups,
            "children": children,
            "children_label": pgettext(_CTX, "Kafedralar") if is_faculty else pgettext(_CTX, "İxtisaslar"),
            "can_assign_members": flags["can_assign_members"],
            "can_assign_head": flags["can_assign_head"],
        }
    )


# ─── Namizəd axtarışı ───────────────────────────────────────────────────────


def _bounds(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", CANDIDATE_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = CANDIDATE_PAGE_SIZE
    return offset, max(1, min(limit, CANDIDATE_MAX_PAGE_SIZE))


@login_required
@require_GET
def structure_role_candidates(request, slug):
    """``?kind=staff|teacher&unit=<id>&q=&offset=&limit=`` — axtarışlı seçici üçün namizədlər.

    Cavab forması layihədəki digər lookup-larla eynidir:
    ``{"results": [{"id", "text"}], "has_more": bool}``. Fail-closed: təyinat
    edə bilməyən aktora namizəd adları SIZMIR (boş 403).
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    flags = registry_flags(request, organization) if scope.has_structure_access else None
    if flags is None or not (flags["can_assign_members"] or flags["can_assign_head"]):
        return JsonResponse({"results": [], "has_more": False}, status=403)

    offset, limit = _bounds(request)
    term = (request.GET.get("q") or "").strip()[:80]
    kind = (request.GET.get("kind") or "staff").strip()

    if kind == "teacher":
        queryset = _teacher_memberships_qs(organization)
        term_q = tolerant_q(term, ("user__first_name", "user__last_name", "user__username"))
        if term_q is not None:
            queryset = queryset.filter(term_q)
        unit_id = (request.GET.get("unit") or "").strip()
        if unit_id:
            queryset = queryset.exclude(scope_unit_id=unit_id)
        page = list(queryset[offset : offset + limit + 1])
        no_chair = pgettext(_CTX, "kafedrasız")
        results = [
            {
                "id": str(m.id),
                "text": f"{_display_name(m.user)} — {m.scope_unit.name if m.scope_unit_id else no_chair}",
            }
            for m in page[:limit]
        ]
        return JsonResponse({"results": results, "has_more": len(page) > limit})

    memberships = head_candidate_memberships(organization, search=term)
    window = head_candidate_rows(memberships[: offset + (limit + 1) * 2])
    page = window[offset : offset + limit]
    return JsonResponse(
        {
            "results": [
                {
                    "id": str(row["user_id"]),
                    "text": f"{row['full_name']} — {row['role_label']}" if row["role_label"] else row["full_name"],
                }
                for row in page
            ],
            "has_more": len(window) > offset + limit,
        }
    )
