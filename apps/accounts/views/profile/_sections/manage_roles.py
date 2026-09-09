"""Profil «Rolları idarə et» bölməsi — TƏŞKİLAT rolları üzrə reyestr.

2026-09-09 yenidən qurulub. Əvvəl bu bölmə köhnə `ProfileRole` enum-undan
(12 ad) oxuyurdu, «Rol təyin et» isə təşkilatın `Role` kataloqundan (onlarla
rol) — nəticədə eyni şəxsin «Proqram koordinatoru» rolu burada nə görünürdü,
nə də verilə bilirdi. İndi hər iki ekran EYNİ mənbədən
(`apps/accounts/services/role_catalog.py`) oxuyur.

Bölmə `ems_ui` komponentləri ilə qurulur: KPI sırası, AVTO filtr paneli,
cədvəl (şəxs · rollar · əsas rol · səviyyə) və rol vermə/geri alma dialoqları.

SORĞU BÜDCƏSİ: siyahı ŞƏXS üzrə səhifələnir (DB tərəfdə); üzvlüklər yalnız
CARİ SƏHİFƏ üçün yüklənir. KPI-lar aqreqat saymalardır — bütün üzvlük sətirləri
yaddaşa alınmır.
"""

from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services.role_catalog import (
    PAGE_SIZE,
    ROLE_CHIP_PREVIEW,
    assignable_roles,
    display_name,
    effective_level,
    initials,
    memberships_by_user,
    primary_membership,
    role_chips,
    role_label,
    role_options,
    role_queryset,
    roles_at_or_above,
    users_holding_roles,
)
from apps.accounts.views._helpers.formatting import _append_query_params
from apps.accounts.views._helpers.tenant import _bind_active_role_context, _get_active_organization

User = get_user_model()

_CTX = "accounts.manage_roles"
_CELLS = "accounts/profile/sections/roles/"

#: Filtr: rol sayına görə süzgəc.
_SHAPE_CHOICES = ("all", "multi", "single")

#: «Heyət» sayılan minimum səviyyə (müəllim və yuxarı).
_STAFF_LEVEL = 50


def _shape_options():
    return [
        {"value": "all", "label": pgettext(_CTX, "Bütün üzvlər")},
        {"value": "multi", "label": pgettext(_CTX, "Birdən çox rolu olanlar")},
        {"value": "single", "label": pgettext(_CTX, "Tək rolu olanlar")},
    ]


def _unit_options(organization):
    from apps.organizations.models import OrgUnit

    options = [{"value": "", "label": pgettext(_CTX, "Bütün bölmələr")}]
    options.extend(
        {"value": str(unit.id), "label": unit.name}
        for unit in OrgUnit.objects.filter(organization=organization, is_active=True)
        .only("id", "name")
        .order_by("name")
    )
    return options


def _members_queryset(organization):
    """Təşkilatın aktiv üzvləri — rol sayı və ən yüksək səviyyə anotasiyası ilə."""
    scope = Q(memberships__organization=organization, memberships__is_active=True, memberships__role__is_active=True)
    return (
        User.objects.filter(scope)
        .annotate(
            top_level=Max("memberships__role__level", filter=scope),
            role_count=Count("memberships__role", distinct=True, filter=scope),
        )
        .distinct()
    )


def _members_with(organization, **membership_filters):
    from apps.organizations.models import Membership

    return Membership.objects.filter(
        organization=organization, is_active=True, role__is_active=True, **membership_filters
    ).values("user_id")


def _row(user, memberships, *, actor_level, is_superadmin, actor_user_id, owner_self):
    name = display_name(user)
    top = primary_membership(memberships)
    target_level = max((effective_level(membership.role) for membership in memberships), default=0)
    is_self = user.pk == actor_user_id
    chips = role_chips(memberships)
    return {
        "user_id": str(user.pk),
        "name": name,
        "username": user.username,
        "email": user.email or "",
        "initials": initials(name),
        "roles": chips,
        "visible_roles": chips[:ROLE_CHIP_PREVIEW],
        "extra_roles": max(0, len(chips) - ROLE_CHIP_PREVIEW),
        "primary_label": role_label(top.role) if top is not None else "",
        "primary_level": effective_level(top.role) if top is not None else 0,
        "level": target_level,
        "role_count": len(chips),
        "can_edit": bool(is_superadmin or (is_self and owner_self) or actor_level > target_level),
    }


def _kpi_tiles(members, *, organization, catalogue, actor_level, is_superadmin):
    # «Redaktə bağlı» sayı sətirlərdəki `can_edit` ilə EYNİ hesabla çıxır —
    # hər ikisi EFFEKTİV səviyyəyə baxır (`Role.level` sütunu RBAC səviyyəsi
    # deyil; bax `role_catalog.effective_level`).
    blocked_roles = [] if is_superadmin else roles_at_or_above(actor_level, catalogue)
    locked = members.filter(pk__in=users_holding_roles(organization, blocked_roles)).count() if blocked_roles else 0
    multi = members.filter(role_count__gt=1).count()
    return [
        {"label": pgettext(_CTX, "Üzv"), "value": members.count(), "tone": "primary"},
        {"label": pgettext(_CTX, "Rol kataloqu"), "value": len(catalogue)},
        {
            "label": pgettext(_CTX, "Çoxlu rollu"),
            "value": multi,
            "tone": "accent-success" if multi else None,
            "note": pgettext(_CTX, "birdən çox təşkilat rolu"),
        },
        {
            "label": pgettext(_CTX, "Heyət"),
            "value": members.filter(top_level__gte=_STAFF_LEVEL).count(),
            "note": pgettext(_CTX, "müəllim və yuxarı səviyyə"),
        },
        {
            "label": pgettext(_CTX, "Redaktə bağlı"),
            "value": locked,
            "tone": "accent-warning" if locked else None,
            "note": pgettext(_CTX, "sizin səviyyənizdən yuxarı"),
        },
    ]


def _table(rows):
    # `_data_table.html` müqaviləsi: birinci sütun sətir başlığıdır (`row_head`),
    # sonuncusu isə əməllər — hər ikisinin başlığı `table_columns`-da olmalıdır.
    columns = [
        {"key": "person", "label": pgettext(_CTX, "Şəxs")},
        {"key": "roles", "label": pgettext(_CTX, "Təşkilat rolları")},
        {"key": "primary", "label": pgettext(_CTX, "Əsas rol")},
        {"key": "level", "label": pgettext(_CTX, "Səviyyə"), "align": "num"},
        {"key": "actions", "label": pgettext(_CTX, "Əməllər")},
    ]
    table_rows = [
        {
            "row_head": row["name"],
            "head_include": f"{_CELLS}_cell_person.html",
            "cells": [
                {"include": f"{_CELLS}_cell_roles.html"},
                {"include": f"{_CELLS}_cell_primary.html"},
                {"text": row["level"], "num": True},
            ],
            "actions_include": f"{_CELLS}_manage_row_actions.html",
            "data": row,
        }
        for row in rows
    ]
    return columns, table_rows


def build_manage_roles_section(request, section, *, capabilities):
    """`section` dict-ini `ems_ui` müqaviləsinə uyğun doldurub qaytarır."""
    organization = _get_active_organization(request)
    is_superadmin = capabilities["is_superadmin"]
    search = (request.GET.get("mr_q") or request.GET.get("manage_roles_search") or "").strip()[:120]
    role_filter = (request.GET.get("mr_role") or "").strip()
    unit_filter = (request.GET.get("mr_unit") or "").strip()
    shape = (request.GET.get("mr_shape") or "").strip()
    shape = shape if shape in _SHAPE_CHOICES else "all"

    section.update(
        {
            "organization": organization,
            "search_query": search,
            "has_access": organization is not None,
            "action_url": reverse("accounts:manage_roles"),
            "post_next_url": _append_query_params(
                reverse("accounts:profile"),
                section="manage-roles",
                mr_q=search,
                mr_role=role_filter,
                mr_unit=unit_filter,
                mr_shape=shape if shape != "all" else "",
            ),
        }
    )

    if organization is None:
        section["access_denied_message"] = pgettext(_CTX, "Rol idarəetməsi üçün aktiv təşkilat tapılmadı.")
        return section

    _bind_active_role_context(
        request.user,
        organization,
        memberships=getattr(request, "org_memberships", []),
        permissions=getattr(request, "org_permissions", []),
    )
    if is_superadmin:
        actor_level = 999
    else:
        actor_level = request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
    owner_self = is_superadmin or getattr(organization, "owner_id", None) == request.user.id

    catalogue = list(role_queryset(organization))
    grantable = list(assignable_roles(organization, actor_level=actor_level, is_superadmin=is_superadmin))

    members = _members_queryset(organization)
    filtered_members = members
    if search:
        filtered_members = filtered_members.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    if role_filter:
        filtered_members = filtered_members.filter(pk__in=_members_with(organization, role_id=role_filter))
    if unit_filter:
        filtered_members = filtered_members.filter(pk__in=_members_with(organization, scope_unit_id=unit_filter))
    if shape == "multi":
        filtered_members = filtered_members.filter(role_count__gt=1)
    elif shape == "single":
        filtered_members = filtered_members.filter(role_count=1)

    page_obj = Paginator(
        filtered_members.order_by("-top_level", "first_name", "last_name", "username"), PAGE_SIZE
    ).get_page(request.GET.get("mr_page"))
    page_users = list(page_obj.object_list)
    grouped = memberships_by_user(organization, user_ids=[user.pk for user in page_users])
    rows = [
        _row(
            user,
            grouped.get(user.pk, []),
            actor_level=actor_level,
            is_superadmin=is_superadmin,
            actor_user_id=request.user.pk,
            owner_self=owner_self,
        )
        for user in page_users
        if grouped.get(user.pk)
    ]
    columns, table_rows = _table(rows)
    filtered = bool(search or role_filter or unit_filter or shape != "all")

    section.update(
        {
            "subtitle": pgettext(
                _CTX,
                "Bir şəxsin bütün təşkilat rolları — məsələn həm «Proqram koordinatoru», həm «Müəllim». "
                "Rol vermək və geri almaq buradan aparılır; hər əməl audit jurnalına yazılır.",
            ),
            "kpi_tiles": _kpi_tiles(
                members,
                organization=organization,
                catalogue=catalogue,
                actor_level=actor_level,
                is_superadmin=is_superadmin,
            ),
            "filter_fields": [
                {
                    "name": "mr_q",
                    "label": pgettext(_CTX, "Axtarış"),
                    "kind": "search",
                    "value": search,
                    "wide": True,
                    "placeholder": pgettext(_CTX, "Ad, istifadəçi adı və ya e-poçt"),
                },
                {
                    "name": "mr_role",
                    "label": pgettext(_CTX, "Rol"),
                    "kind": "select",
                    "options": role_options(catalogue, placeholder=pgettext(_CTX, "Bütün rollar")),
                    "value": role_filter,
                    "searchable": True,
                },
                {
                    "name": "mr_unit",
                    "label": pgettext(_CTX, "Bölmə"),
                    "kind": "select",
                    "options": _unit_options(organization),
                    "value": unit_filter,
                    "searchable": True,
                },
                {
                    "name": "mr_shape",
                    "label": pgettext(_CTX, "Rol sayı"),
                    "kind": "select",
                    "options": _shape_options(),
                    "value": shape,
                    "default": "all",
                },
            ],
            "filter_count_label": pgettext(_CTX, "Nəticə: %(n)d nəfər") % {"n": page_obj.paginator.count},
            "columns": columns,
            "table_rows": table_rows,
            "table_state": "ready" if table_rows else "empty",
            "page_obj": page_obj,
            "pagination_query": urlencode(
                {
                    key: value
                    for key, value in {
                        "section": "manage-roles",
                        "mr_q": search,
                        "mr_role": role_filter,
                        "mr_unit": unit_filter,
                        "mr_shape": shape if shape != "all" else "",
                    }.items()
                    if value
                }
            ),
            "state_title": (
                pgettext(_CTX, "Filtrə uyğun üzv yoxdur")
                if filtered
                else pgettext(_CTX, "Hələ idarə ediləcək üzv yoxdur")
            ),
            "state_body": (
                pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.")
                if filtered
                else pgettext(_CTX, "Təşkilata üzv əlavə edildikcə siyahı burada görünəcək.")
            ),
            "grantable_roles": [
                {"value": str(role.id), "label": f"{role_label(role)} ({role.level})"} for role in grantable
            ],
            "unit_options": _unit_options(organization),
            "can_grant": bool(grantable),
            # `_form_dialog.html` gizli sahələri — əməl adı + qayıdış URL-i
            # sabitdir, hədəf (`user_id`/`membership_id`) sətir düyməsindən
            # `data-roles-prefill` ilə doldurulur (`roles_ui.js`).
            "grant_hidden": [
                {"name": "action", "value": "grant_role"},
                {"name": "next", "value": section["post_next_url"]},
                {"name": "user_id", "value": ""},
            ],
            "revoke_hidden": [
                {"name": "action", "value": "revoke_role"},
                {"name": "next", "value": section["post_next_url"]},
                {"name": "membership_id", "value": ""},
            ],
        }
    )
    return section
