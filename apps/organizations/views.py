"""
Views for the organizations app.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Organization


@login_required
def select_organization(request):
    """
    View for selecting/switching active organization.
    """
    # Get all organizations user is a member of
    user_memberships = request.user.memberships.filter(is_active=True).select_related(
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
    has_membership = request.user.memberships.filter(
        organization=organization, is_active=True
    ).exists()

    if not has_membership:
        messages.error(request, "You don't have access to this organization.")
        return redirect("organizations:select")

    # Set active organization in session
    request.session["active_organization"] = organization.slug
    messages.success(request, f"Switched to {organization.name}")

    # Redirect to next or home
    next_url = request.GET.get("next", "/")
    return redirect(next_url)


# Placeholder views - to be implemented in Sprint 6
