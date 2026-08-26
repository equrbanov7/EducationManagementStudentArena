"""Organizations — idarəetmə səhifələrinin context builder-ləri (F5, 2026-07-02).

QEYD: accounts profil dashboard-u build_* funksiyalarını lazy import edir —
fasad (views/__init__) bu adları ixrac etməyə davam edir."""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse

from core.constants import OrgUnitType

from ...models import OrgUnit
from ..shared._helpers import (
    _can_manage_organization,
    _can_view_structure,
    _get_structure_scope,
    _has_org_permission,
    _unique_unit_slug,
    _visible_units_queryset,
)


def build_organization_structure_context(
    request,
    organization,
    *,
    form_errors=None,
    form_values=None,
    notice="",
):
    """
    Build the lightweight structure context used by both the full page and
    profile AJAX section. Lists are split by unit type to avoid recursive
    template traversal and unnecessary prefetch depth.
    """
    scope = _get_structure_scope(request, organization)
    can_view = _can_view_structure(request, organization, scope)
    unit_create_allowed = _can_manage_organization(request.user, organization) or _has_org_permission(
        request,
        "unit.create",
    )

    if scope.is_unit_scoped:
        units = list(
            OrgUnit.objects.filter(organization=organization, pk__in=scope.unit_ids, is_active=True)
            .prefetch_related("children")
            .order_by("order", "name")
        )
    else:
        units = list(
            organization.units.filter(parent=None, is_active=True)
            .prefetch_related("children", "children__children")
            .order_by("order", "name")
        )

    visible_units = _visible_units_queryset(organization, scope)
    faculties = list(
        visible_units.filter(unit_type=OrgUnitType.FACULTY)
        .only("id", "organization_id", "parent_id", "unit_type", "name", "slug", "code", "path", "level", "order")
        .order_by("name")
    )
    kafedras = list(
        visible_units.filter(unit_type__in=[OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT])
        .select_related("parent")
        .only(
            "id",
            "organization_id",
            "parent_id",
            "unit_type",
            "name",
            "slug",
            "code",
            "path",
            "level",
            "order",
            "parent__id",
            "parent__name",
        )
        .order_by("parent__name", "name")
    )

    return {
        "organization": organization,
        "units": units,
        "unit_scope": scope,
        "can_view": can_view,
        "faculties": faculties,
        "kafedras": kafedras,
        "faculty_count": len(faculties),
        "kafedra_count": len(kafedras),
        "unit_total_count": visible_units.count(),
        "can_create_faculty": unit_create_allowed and scope.is_org_wide,
        "can_create_kafedra": unit_create_allowed and bool(faculties),
        "faculty_parent_options": faculties,
        "form_errors": form_errors or {},
        "form_values": form_values or {},
        "notice": notice,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


def _create_structure_unit(request, organization):
    scope = _get_structure_scope(request, organization)
    if not _can_view_structure(request, organization, scope):
        return False, {"general": "Bu struktur bölməsini idarə etmək üçün icazəniz yoxdur."}

    if not (_can_manage_organization(request.user, organization) or _has_org_permission(request, "unit.create")):
        return False, {"general": "Yeni fakültə və ya kafedra yaratmaq üçün `unit.create` icazəsi tələb olunur."}

    unit_kind = (request.POST.get("unit_kind") or "").strip()
    name = (request.POST.get("name") or "").strip()
    code = (request.POST.get("code") or "").strip()[:50]
    errors = {}

    if unit_kind not in {"faculty", "kafedra"}:
        errors["general"] = "Yaradılacaq struktur növü düzgün seçilməyib."
    if not name:
        errors["name"] = "Ad sahəsi mütləqdir."
    elif len(name) > 255:
        errors["name"] = "Ad maksimum 255 simvol ola bilər."

    parent = None
    unit_type = OrgUnitType.FACULTY
    if unit_kind == "faculty":
        if not scope.is_org_wide:
            errors["general"] = "Yeni fakültə yalnız bütün təşkilatı idarə edən istifadəçi tərəfindən yaradıla bilər."
    elif unit_kind == "kafedra":
        unit_type = OrgUnitType.CHAIR
        parent_id = (request.POST.get("parent") or "").strip()
        if not parent_id:
            errors["parent"] = "Kafedra üçün fakültə seçilməlidir."
        else:
            faculty_qs = _visible_units_queryset(organization, scope).filter(unit_type=OrgUnitType.FACULTY)
            parent = faculty_qs.filter(pk=parent_id).first()
            if parent is None:
                errors["parent"] = "Seçilmiş fakültəyə bu istifadəçi ilə giriş yoxdur."

    if errors:
        return False, errors

    with transaction.atomic():
        OrgUnit.objects.create(
            organization=organization,
            parent=parent,
            unit_type=unit_type,
            name=name,
            slug=_unique_unit_slug(organization, name, unit_kind),
            code=code,
        )
    return True, {}


def _structure_ajax_response(request, context, *, status=200):
    context = dict(context)
    context.update(
        {
            "active_section": "org-structure",
            "profile_base_url": reverse("accounts:profile"),
            "embedded_in_profile": True,
        }
    )
    context["org_structure_section"] = context
    html = render_to_string("accounts/profile/sections/_org_structure.html", context, request=request)
    return JsonResponse(
        {
            "ok": status < 400,
            "section": "org-structure",
            "html": html,
        },
        status=status,
    )


def _has_org_wide_membership(user, organization) -> bool:
    """İstifadəçinin bu təşkilatda ORGANIZATION scope-lu aktiv rolu varmı?

    Belə rol (HR, org_admin, imtahan mərkəzi…) bütün təşkilatı görməkdə
    haqlıdır; UNIT scope-lu rol isə yalnız öz alt-ağacını görməlidir və
    ``scope_unit`` boşdursa sahəsi müəyyən deyil → heç nə (QA B-2).
    """

    from core.constants import RoleScopeType

    from ...services import get_active_memberships

    return any(
        membership.role.scope_type == RoleScopeType.ORGANIZATION
        for membership in get_active_memberships(user, organization)
    )


def build_organization_members_context(request, organization):
    from ...scoping import get_unit_scope, scope_memberships_by_unit
    from ...services import get_user_org_role_level

    scope = get_unit_scope(request.user, organization, request=request)
    can_view_members = _can_manage_organization(request.user, organization) or (
        _has_org_permission(request, "member.view")
        and (scope.is_unit_scoped or get_user_org_role_level(request.user, organization) >= 65)
    )

    members = organization.memberships.filter(is_active=True).select_related("user", "role", "scope_unit")
    if scope.is_unit_scoped:
        members = scope_memberships_by_unit(members, scope, organization)
    elif not scope.is_org_wide and not _has_org_wide_membership(request.user, organization):
        # QA 2026-08-28 (B-2): scope_unit-i TƏYİN EDİLMƏMİŞ unit-rolu (dekan,
        # kafedra müdiri) əvvəllər filtrsiz keçib BÜTÜN təşkilatın üzv siyahısını
        # görürdü — sahəsi müəyyən olmayan rol heç nə görməməlidir (fail-closed).
        # Org-səviyyəli rollar (HR, org_admin və s.) bu qoldan təsirlənmir.
        members = members.none()

    role_filter = (request.GET.get("role") or "").strip()
    if role_filter:
        members = members.filter(role__name=role_filter)

    search = (request.GET.get("search") or "").strip()[:120]
    if search:
        members = members.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    members = members.order_by("-role__level", "user__username")
    members_page = Paginator(members, 25).get_page(request.GET.get("members_page"))
    roles = organization.roles.filter(is_active=True).order_by("name")
    pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "section": "org-members" if request.GET.get("section") == "org-members" else "",
                "search": search,
                "role": role_filter,
            }.items()
            if value
        }
    )

    return {
        "organization": organization,
        "members": members_page,
        "members_page_obj": members_page,
        "roles": roles,
        "current_role": role_filter,
        "search_query": search,
        "can_view": can_view_members,
        "members_pagination_query": pagination_query,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


def build_organization_roles_context(request, organization):
    from ...permissions import PERMISSION_CATEGORIES

    return {
        "organization": organization,
        "roles": organization.roles.all().order_by("-level", "name"),
        "permission_categories": PERMISSION_CATEGORIES,
        "can_view": _can_manage_organization(request.user, organization),
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }
