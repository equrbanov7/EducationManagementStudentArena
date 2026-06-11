"""
Views for the organizations app.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.helpers import _safe_same_origin_redirect_path

from .models import Organization, OrgUnit
from .services import can_user_manage_org, is_tenant_accessible_organization


def _is_ajax_request(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _can_access_organization(user, organization):
    if not getattr(user, "is_authenticated", False):
        return False

    if not is_tenant_accessible_organization(organization):
        return False

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True

    if getattr(organization, "owner_id", None) == user.id:
        return True

    return user.memberships.filter(organization=organization, organization__status="active", is_active=True).exists()


def _can_manage_organization(user, organization):
    if not _can_access_organization(user, organization):
        return False

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True

    return can_user_manage_org(user, organization)


def _has_org_permission(request, permission):
    from .permissions import has_permission

    return has_permission(list(getattr(request, "org_permissions", []) or []), permission)


def _unique_unit_slug(organization, name, fallback):
    base_slug = slugify(name) or fallback
    slug = base_slug
    suffix = 2
    while OrgUnit.objects.filter(organization=organization, slug=slug).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def _get_structure_scope(request, organization):
    from .scoping import get_unit_scope

    return get_unit_scope(request.user, organization, request=request)


def _can_view_structure(request, organization, scope):
    return scope.is_org_wide or _has_org_permission(request, "unit.view")


def _visible_units_queryset(organization, scope):
    units = OrgUnit.objects.filter(organization=organization, is_active=True)
    if scope.is_unit_scoped:
        units = units.filter(scope.unit_subtree_q())
    return units


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


def build_organization_members_context(request, organization):
    from .scoping import get_unit_scope, scope_memberships_by_unit
    from .services import get_user_org_role_level

    scope = get_unit_scope(request.user, organization, request=request)
    can_view_members = _can_manage_organization(request.user, organization) or (
        _has_org_permission(request, "member.view")
        and (scope.is_unit_scoped or get_user_org_role_level(request.user, organization) >= 65)
    )

    members = organization.memberships.filter(is_active=True).select_related("user", "role", "scope_unit")
    if scope.is_unit_scoped:
        members = scope_memberships_by_unit(members, scope, organization)

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
    from .permissions import PERMISSION_CATEGORIES

    return {
        "organization": organization,
        "roles": organization.roles.all().order_by("-level", "name"),
        "permission_categories": PERMISSION_CATEGORIES,
        "can_view": _can_manage_organization(request.user, organization),
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


@login_required
def select_organization(request):
    """
    View for selecting/switching active organization.
    """
    is_superadmin = getattr(request.user, "is_superuser", False) or getattr(request.user, "is_superadmin", False)

    # Get all organizations user is a member of
    user_memberships = request.user.memberships.filter(is_active=True, organization__status="active").select_related(
        "organization", "role"
    )

    organizations = {}
    for membership in user_memberships:
        org = membership.organization
        if org.is_active:
            if org.id not in organizations:
                organizations[org.id] = {
                    "organization": org,
                    "memberships": [],
                }
            organizations[org.id]["memberships"].append(membership)

    owned_organizations = Organization.objects.filter(owner=request.user, is_active=True, status="active").order_by(
        "name"
    )
    for organization in owned_organizations:
        organizations.setdefault(
            organization.id,
            {
                "organization": organization,
                "memberships": [],
            },
        )

    if is_superadmin:
        for organization in (
            Organization.objects.filter(is_active=True, status="active").select_related("owner").order_by("name")
        ):
            organizations.setdefault(
                organization.id,
                {
                    "organization": organization,
                    "memberships": [],
                },
            )

    next_url = request.GET.get("next", "")
    for org_data in organizations.values():
        role_labels = [membership.role.display_name for membership in org_data["memberships"]]
        if org_data["organization"].owner_id == request.user.id and "Təşkilat Sahibi" not in role_labels:
            role_labels.insert(0, "Təşkilat Sahibi")
        if is_superadmin and not role_labels:
            role_labels.append("Super Admin")
        org_data["role_labels"] = role_labels
        default_next_url = reverse("organizations:dashboard", kwargs={"slug": org_data["organization"].slug})
        target_next_url = next_url or default_next_url
        org_data["switch_url"] = "{}?{}".format(
            reverse("organizations:switch", kwargs={"slug": org_data["organization"].slug}),
            urlencode({"next": target_next_url}),
        )

    context = {
        "organizations": sorted(organizations.values(), key=lambda item: item["organization"].name.lower()),
        "current_org": request.organization,
    }

    return render(request, "organizations/select_organization.html", context)


@login_required
def switch_organization(request, slug):
    """
    Switch to a different organization.
    """
    # Verify user has access to this organization
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Set active organization in session
    request.session["active_organization"] = organization.slug
    messages.success(
        request,
        pgettext("organizations.views.message", "switched_to_org").format(organization=organization.name),
    )

    # Redirect to next or home (with validation to prevent open redirect)
    next_url = request.GET.get("next", "")
    safe_path = _safe_same_origin_redirect_path(request, next_url)
    if safe_path:
        return redirect(safe_path)
    return redirect("organizations:dashboard", slug=organization.slug)


# Sprint 6: Dashboard and Management Views


@login_required
def organization_dashboard(request, slug):
    """
    Organization dashboard with stats and recent activity.
    """
    from apps.audit.models import AuditLog

    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Set as active organization
    request.session["active_organization"] = organization.slug

    # Get stats
    stats = {
        "total_members": organization.memberships.filter(is_active=True).count(),
        "total_units": organization.units.filter(is_active=True).count(),
        "total_roles": organization.roles.filter(is_active=True).count(),
    }

    # Get recent activity from audit log
    recent_activity = (
        AuditLog.objects.filter(organization=organization).select_related("user").order_by("-created_at")[:10]
    )

    # Get user's memberships in this org
    user_memberships = request.user.memberships.filter(organization=organization, is_active=True).select_related("role")

    context = {
        "organization": organization,
        "stats": stats,
        "recent_activity": recent_activity,
        "user_memberships": user_memberships,
    }

    return render(request, "organizations/dashboard.html", context)


@login_required
def organization_structure(request, slug):
    """
    Organization structure management with tree view of units.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    scope = _get_structure_scope(request, organization)

    # Struktur səhifəsi idarəetmə səhifəsidir: yalnız org-wide idarəetmə scope-u
    # və ya `unit.view` icazəsi olanlar (rektor/admin, dekan, kafedra müdürü,
    # HR, imtahan mərkəzi) görə bilər. Adi tələbənin scope_unit-i olsa belə
    # `unit.view` icazəsi olmadığı üçün bura düşmür.
    if not _can_view_structure(request, organization, scope):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:dashboard", slug=organization.slug)

    form_errors = {}
    form_values = {}
    notice = ""
    if request.method == "POST":
        form_values = {
            "unit_kind": (request.POST.get("unit_kind") or "").strip(),
            "name": (request.POST.get("name") or "").strip(),
            "code": (request.POST.get("code") or "").strip(),
            "parent": (request.POST.get("parent") or "").strip(),
        }
        created, form_errors = _create_structure_unit(request, organization)
        if created:
            notice = "Struktur bölməsi yaradıldı."
            if _is_ajax_request(request):
                context = build_organization_structure_context(request, organization, notice=notice)
                return _structure_ajax_response(request, context)
            messages.success(request, notice)
            return redirect("organizations:structure", slug=organization.slug)
        if not _is_ajax_request(request):
            messages.error(request, form_errors.get("general") or "Struktur bölməsi yaradıla bilmədi.")

    context = build_organization_structure_context(
        request,
        organization,
        form_errors=form_errors,
        form_values=form_values,
        notice=notice,
    )
    context["org_structure_section"] = context

    if request.method == "POST" and _is_ajax_request(request):
        return _structure_ajax_response(request, context, status=400)

    return render(request, "organizations/structure.html", context)


@login_required
def organization_members(request, slug):
    """
    Member management with filters and search.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Giriş qaydası:
    # - idarəetmə levli (≥80, rektor/prorektor/org admin/dekan və s.) → icazəlidir
    # - `member.view` icazəli org-scope rollar (HR, imtahan mərkəzi) → icazəlidir
    # - `member.view` icazəli unit-scoped istifadəçilər → yalnız öz alt-ağacı
    context = build_organization_members_context(request, organization)
    if not context["can_view"]:
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")
    context["org_members_section"] = context

    return render(request, "organizations/members.html", context)


@login_required
def organization_roles(request, slug):
    """
    Role management with permission matrix.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_manage_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    context = build_organization_roles_context(request, organization)
    context["org_roles_section"] = context

    return render(request, "organizations/roles.html", context)


@login_required
def organization_settings(request, slug):
    """
    Organization settings page.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    is_superadmin = getattr(request.user, "is_superuser", False) or getattr(request.user, "is_superadmin", False)
    is_owner = organization.owner == request.user

    if not is_superadmin and not is_owner:
        # Check if user has admin role
        has_admin = request.user.memberships.filter(
            organization=organization, organization__status="active", role__level__gte=90, is_active=True
        ).exists()

        if not has_admin:
            messages.error(request, pgettext("organizations.views.message", "no_settings_access"))
            return redirect("organizations:dashboard", slug=slug)

    if request.method == "POST":
        # Update organization settings
        organization.description = request.POST.get("description", "")
        organization.email = request.POST.get("email", "")
        organization.phone = request.POST.get("phone", "")
        organization.address = request.POST.get("address", "")
        organization.website = request.POST.get("website", "")
        organization.save()

        messages.success(request, pgettext("organizations.views.message", "settings_updated"))
        return redirect("organizations:settings", slug=slug)

    context = {
        "organization": organization,
        "is_owner": is_owner or is_superadmin,
    }

    return render(request, "organizations/settings.html", context)
