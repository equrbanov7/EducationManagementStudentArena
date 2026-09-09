"""Profil «Rol təyin et» bölməsi — təşkilat daxili ƏSAS rol (səviyyəli rol).

2026-09-09 yenidən qurulub. Siyahı artıq ÜZVLÜK sətirləri deyil, ŞƏXS üzrədir:
bir nəfərin bütün təşkilat rolları bir sətirdə nişan kimi görünür (əvvəl eyni
adam neçə üzvlüyü varsa o qədər sətirdə təkrarlanırdı və «hansı sətir düzdür?»
sualı yaranırdı — sahib şikayəti «baş qarışır»).

Bölgü:
  * «Rol təyin et»    — şəxsin ƏSAS (ən yüksək) üzvlüyünün rolunu dəyişir və
    təşkilata yeni şəxs əlavə edir (bu ekran);
  * «Rolları idarə et» — ƏLAVƏ rolları verir/geri alır (`manage_roles.py`).
Hər ikisi EYNİ kataloqdan (`services/role_catalog.py`) oxuyur.
"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.models import UserProfile
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
from apps.accounts.views._helpers.membership import _pending_student_request_queryset
from apps.notifications.models import StudentOrganizationRequestStatus

_CTX = "accounts.role_assignment"
_CELLS = "accounts/profile/sections/roles/"

PENDING_PAGE_SIZE = 10


def _members_queryset(organization, *, actor_level, is_superadmin, catalogue):
    """Aktorun dəyişə bildiyi üzvlər — səviyyə qapısı SERVERLƏ eyni hesabla.

    DİQQƏT: süzgəc `Role.level` sütunu ilə APARILMIR. Kataloq rəqəmi RBAC
    səviyyəsi deyil (universitet seed-ində «Dekan» 80/90) — köhnə kod
    `role__level__lt` işlədirdi və nəticədə dekan başqa dekanı siyahıda görüb
    «Rolu yenilə» basırdı, server isə rədd edirdi. İndi effektiv səviyyəsi
    aktorunkundan aşağı OLMAYAN rolları daşıyanlar tam çıxarılır.
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    scope = Q(memberships__organization=organization, memberships__is_active=True, memberships__role__is_active=True)
    queryset = (
        user_model.objects.filter(scope)
        .annotate(
            top_level=Max("memberships__role__level", filter=scope),
            role_count=Count("memberships__role", distinct=True, filter=scope),
        )
        .distinct()
    )
    if not is_superadmin:
        blocked = roles_at_or_above(actor_level, catalogue)
        if blocked:
            queryset = queryset.exclude(pk__in=users_holding_roles(organization, blocked))
    return queryset


def _member_row(user, memberships, *, organization):
    name = display_name(user)
    top = primary_membership(memberships)
    chips = role_chips(memberships)
    return {
        "user_id": str(user.pk),
        "membership_id": str(top.id) if top is not None else "",
        "role_id": str(top.role_id) if top is not None else "",
        "name": name,
        "username": user.username,
        "email": user.email or "",
        "initials": initials(name),
        "roles": chips,
        "visible_roles": chips[:ROLE_CHIP_PREVIEW],
        "extra_roles": max(0, len(chips) - ROLE_CHIP_PREVIEW),
        "primary_label": role_label(top.role) if top is not None else "",
        "primary_level": effective_level(top.role) if top is not None else 0,
        "old_role": f"{role_label(top.role)} ({top.role.level})" if top is not None else "",
        "organization_name": organization.name,
        "scope": top.scope_unit.name if (top is not None and top.scope_unit_id) else "",
    }


def _pending_row(profile, *, organization):
    user = profile.user
    name = display_name(user)
    requested = ""
    if profile.requested_organization_id:
        requested = profile.requested_organization.name
    elif profile.requested_organization_name:
        requested = profile.requested_organization_name
    return {
        "user_id": str(user.pk),
        "name": name,
        "username": user.username,
        "email": user.email or "",
        "initials": initials(name),
        "requested": requested,
        "organization_name": organization.name,
    }


def _member_table(rows):
    columns = [
        {"key": "person", "label": pgettext(_CTX, "Şəxs")},
        {"key": "roles", "label": pgettext(_CTX, "Cari rollar")},
        {"key": "level", "label": pgettext(_CTX, "Səviyyə"), "align": "num"},
        {"key": "new_role", "label": pgettext(_CTX, "Dəyişəcək rol")},
    ]
    table_rows = [
        {
            "row_head": row["name"],
            "head_include": f"{_CELLS}_cell_person.html",
            "cells": [
                {"include": f"{_CELLS}_cell_roles.html"},
                {"text": row["primary_level"], "num": True},
                {"include": f"{_CELLS}_cell_role_picker.html"},
            ],
            "data": row,
        }
        for row in rows
    ]
    return columns, table_rows


def _pending_table(rows):
    columns = [
        {"key": "person", "label": pgettext(_CTX, "Şəxs")},
        {"key": "email", "label": pgettext(_CTX, "E-poçt")},
        {"key": "requested", "label": pgettext(_CTX, "Müraciət etdiyi təşkilat")},
        {"key": "role", "label": pgettext(_CTX, "Veriləcək rol")},
    ]
    table_rows = [
        {
            "row_head": row["name"],
            "head_include": f"{_CELLS}_cell_person.html",
            "cells": [
                {"text": row["email"], "muted": not row["email"]},
                {"text": row["requested"] or "—", "muted": not row["requested"]},
                {"include": f"{_CELLS}_cell_attach_picker.html"},
            ],
            "data": row,
        }
        for row in rows
    ]
    return columns, table_rows


def _unassigned_queryset(request, organization, *, is_superadmin, search):
    queryset = UserProfile.objects.filter(user__is_active=True, organization__isnull=True).select_related(
        "user", "requested_organization"
    )
    if not is_superadmin:
        pending_request_user_ids = _pending_student_request_queryset(
            organization=organization,
            statuses=[StudentOrganizationRequestStatus.PENDING],
        ).values_list("user_id", flat=True)
        queryset = queryset.filter(
            Q(user_id__in=pending_request_user_ids)
            | Q(requested_organization=organization)
            | Q(
                requested_organization__isnull=True,
                requested_organization_name__iexact=organization.name,
            )
        )
    if search:
        queryset = queryset.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )
    return queryset.order_by("user__username")


def build_role_assignment_section(
    request,
    section,
    *,
    management_org,
    management_can_assign_roles,
    management_min_level_ok,
    management_user_level,
    capabilities,
):
    """`section` dict-ini `ems_ui` müqaviləsinə uyğun doldurub qaytarır."""
    is_superadmin = capabilities["is_superadmin"]
    search = (request.GET.get("ra_q") or request.GET.get("q") or request.GET.get("search") or "").strip()[:120]
    role_filter = (request.GET.get("ra_role") or "").strip()
    unassigned_search = (request.GET.get("unassigned_search") or "").strip()[:120]

    section.update(
        {
            "organization": management_org,
            "search_query": search,
            "unassigned_search_query": unassigned_search,
            "can_assign_roles": management_can_assign_roles,
            "has_access": management_org is not None and management_min_level_ok,
            "action_url": reverse("accounts:role_assignment"),
            "subtitle": pgettext(
                _CTX,
                "Təşkilat daxili rol (səviyyəli rol) — şəxsin əsas rolunu dəyişin və ya yeni şəxsi təşkilata "
                "əlavə edin. Əlavə rollar «Rolları idarə et» bölməsindədir.",
            ),
            "post_next_url": _append_query_params(
                reverse("accounts:profile"),
                section="role-assignment",
                ra_q=search,
                ra_role=role_filter,
                unassigned_search=unassigned_search,
                ra_page=request.GET.get("ra_page", ""),
                ra_pending_page=request.GET.get("ra_pending_page", ""),
            ),
        }
    )

    if management_org is None:
        section["access_denied_message"] = pgettext(_CTX, "Aktiv təşkilat tapılmadı.")
        return section
    if not management_min_level_ok:
        section["access_denied_message"] = pgettext(
            _CTX, "Bu bölmə üçün minimum müəllim və ya daha yüksək səviyyə tələb olunur."
        )
        return section

    actor_level = 999 if is_superadmin else management_user_level
    catalogue = list(role_queryset(management_org))
    grantable = list(assignable_roles(management_org, actor_level=actor_level, is_superadmin=is_superadmin))

    members = _members_queryset(
        management_org, actor_level=actor_level, is_superadmin=is_superadmin, catalogue=catalogue
    )
    filtered = members
    if search:
        filtered = filtered.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    if role_filter:
        from apps.organizations.models import Membership

        filtered = filtered.filter(
            pk__in=Membership.objects.filter(organization=management_org, is_active=True, role_id=role_filter).values(
                "user_id"
            )
        )

    page_obj = Paginator(filtered.order_by("-top_level", "first_name", "last_name", "username"), PAGE_SIZE).get_page(
        request.GET.get("ra_page")
    )
    page_users = list(page_obj.object_list)
    grouped = memberships_by_user(management_org, user_ids=[user.pk for user in page_users])
    member_rows = [
        _member_row(user, grouped[user.pk], organization=management_org) for user in page_users if grouped.get(user.pk)
    ]
    columns, table_rows = _member_table(member_rows)

    pending_page = Paginator(
        _unassigned_queryset(request, management_org, is_superadmin=is_superadmin, search=unassigned_search),
        PENDING_PAGE_SIZE,
    ).get_page(request.GET.get("ra_pending_page"))
    pending_rows = [_pending_row(profile, organization=management_org) for profile in pending_page.object_list]
    pending_columns, pending_table_rows = _pending_table(pending_rows)

    no_role_members = members.filter(top_level__lt=50).count()
    is_filtered = bool(search or role_filter)
    base_params = {
        "section": "role-assignment",
        "ra_q": search,
        "ra_role": role_filter,
        "unassigned_search": unassigned_search,
    }

    section.update(
        {
            "assignable_roles": grantable,
            "role_choices": role_options(grantable),
            "kpi_tiles": [
                {"label": pgettext(_CTX, "İdarə edilə bilən üzv"), "value": members.count(), "tone": "primary"},
                {"label": pgettext(_CTX, "Rol kataloqu"), "value": len(grantable)},
                {
                    "label": pgettext(_CTX, "Heyət"),
                    "value": members.filter(top_level__gte=50).count(),
                    "note": pgettext(_CTX, "müəllim və yuxarı"),
                },
                {"label": pgettext(_CTX, "Tələbə səviyyəsi"), "value": no_role_members},
                {
                    "label": pgettext(_CTX, "Gözləyən"),
                    "value": pending_page.paginator.count,
                    "tone": "accent-warning" if pending_page.paginator.count else None,
                    "note": pgettext(_CTX, "təşkilata qoşulmaq istəyir"),
                },
            ],
            "filter_fields": [
                {
                    "name": "ra_q",
                    "label": pgettext(_CTX, "Axtarış"),
                    "kind": "search",
                    "value": search,
                    "wide": True,
                    "placeholder": pgettext(_CTX, "Ad, istifadəçi adı və ya e-poçt"),
                },
                {
                    "name": "ra_role",
                    "label": pgettext(_CTX, "Rol"),
                    "kind": "select",
                    "options": role_options(grantable, placeholder=pgettext(_CTX, "Bütün rollar")),
                    "value": role_filter,
                    "searchable": True,
                },
            ],
            "filter_count_label": pgettext(_CTX, "Nəticə: %(n)d nəfər") % {"n": page_obj.paginator.count},
            "columns": columns,
            "table_rows": table_rows,
            "table_state": "ready" if table_rows else "empty",
            "page_obj": page_obj,
            "pagination_query": urlencode({key: value for key, value in base_params.items() if value}),
            "state_title": (
                pgettext(_CTX, "Filtrə uyğun üzv yoxdur") if is_filtered else pgettext(_CTX, "Hələ üzv yoxdur")
            ),
            "state_body": (
                pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.")
                if is_filtered
                else pgettext(_CTX, "Aşağıdakı «Gözləyən müraciətlər» siyahısından şəxsi təşkilata əlavə edin.")
            ),
            "pending_columns": pending_columns,
            "pending_rows": pending_table_rows,
            "pending_state": "ready" if pending_table_rows else "empty",
            "pending_page_obj": pending_page,
            "pending_pagination_query": urlencode({key: value for key, value in base_params.items() if value}),
            "pending_state_title": pgettext(_CTX, "Gözləyən müraciət yoxdur"),
            "pending_state_body": pgettext(
                _CTX, "Təşkilata qoşulmaq üçün müraciət edən şəxs olmadıqda bu siyahı boş qalır."
            ),
        }
    )
    return section
