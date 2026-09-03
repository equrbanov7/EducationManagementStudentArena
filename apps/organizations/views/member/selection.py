"""Organizations — üzv səthi: təşkilat seçimi/keçidi (F5 rol-skeleti, 2026-07-02)."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from core.helpers import _safe_same_origin_redirect_path
from core.staff_position import visible_role_label

from ...models import Organization
from ..shared._helpers import _can_access_organization


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
        # ⚠️ Doldurucu «Üzv» rolu nişan kimi göstərilmir (core/staff_position.py).
        role_labels = [
            label
            for label in (
                visible_role_label(membership.role.name, membership.role.display_name)
                for membership in org_data["memberships"]
            )
            if label
        ]
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
