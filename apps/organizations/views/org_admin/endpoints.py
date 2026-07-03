"""Organizations — owner/admin idarə səhifələri (F5 rol-skeleti, 2026-07-02)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext

from ...models import Organization
from ..shared._helpers import (
    _can_access_organization,
    _can_manage_organization,
    _can_view_structure,
    _get_structure_scope,
    _is_ajax_request,
)
from .context import (
    _create_structure_unit,
    _structure_ajax_response,
    build_organization_members_context,
    build_organization_roles_context,
    build_organization_structure_context,
)


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
            messages.error(
                request,
                form_errors.get("general")
                or pgettext("organizations.views.message", "Struktur bölməsi yaradıla bilmədi."),
            )

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
