"""
Views for the organizations app.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext

from core.helpers import _safe_same_origin_redirect_path

from .models import Organization


@login_required
def select_organization(request):
    """
    View for selecting/switching active organization.
    """
    # Get all organizations user is a member of
    user_memberships = request.user.memberships.filter(is_active=True).select_related("organization", "role")

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

    context = {
        "organizations": list(organizations.values()),
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

    # Check if user is a member
    has_membership = request.user.memberships.filter(organization=organization, is_active=True).exists()

    if not has_membership:
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
    return redirect("/")


# Sprint 6: Dashboard and Management Views


@login_required
def organization_dashboard(request, slug):
    """
    Organization dashboard with stats and recent activity.
    """
    from apps.audit.models import AuditLog

    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user has access
    has_membership = request.user.memberships.filter(organization=organization, is_active=True).exists()

    if not has_membership:
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

    # Check if user has access
    has_membership = request.user.memberships.filter(organization=organization, is_active=True).exists()

    if not has_membership:
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Get all units in tree structure
    units = organization.units.filter(parent=None).prefetch_related("children", "children__children").order_by("order")

    context = {
        "organization": organization,
        "units": units,
    }

    return render(request, "organizations/structure.html", context)


@login_required
def organization_members(request, slug):
    """
    Member management with filters and search.
    """
    from django.db.models import Q

    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user has access
    has_membership = request.user.memberships.filter(organization=organization, is_active=True).exists()

    if not has_membership:
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Get members with filters
    members = organization.memberships.filter(is_active=True).select_related("user", "role", "scope_unit")

    # Filter by role
    role_filter = request.GET.get("role")
    if role_filter:
        members = members.filter(role__name=role_filter)

    # Search by name or email
    search = request.GET.get("search")
    if search:
        members = members.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    # Get all roles for filter
    roles = organization.roles.filter(is_active=True).order_by("name")

    context = {
        "organization": organization,
        "members": members,
        "roles": roles,
        "current_role": role_filter,
        "search_query": search,
    }

    return render(request, "organizations/members.html", context)


@login_required
def organization_roles(request, slug):
    """
    Role management with permission matrix.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user has access
    has_membership = request.user.memberships.filter(organization=organization, is_active=True).exists()

    if not has_membership:
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Get all roles
    roles = organization.roles.all().order_by("-level")

    # Get permission categories
    from .permissions import PERMISSION_CATEGORIES

    context = {
        "organization": organization,
        "roles": roles,
        "permission_categories": PERMISSION_CATEGORIES,
    }

    return render(request, "organizations/roles.html", context)


@login_required
def organization_settings(request, slug):
    """
    Organization settings page.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user has access and is owner
    is_owner = organization.owner == request.user

    if not is_owner:
        # Check if user has admin role
        has_admin = request.user.memberships.filter(
            organization=organization, role__level__gte=90, is_active=True
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
        "is_owner": is_owner,
    }

    return render(request, "organizations/settings.html", context)
