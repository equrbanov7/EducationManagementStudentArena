"""
Superadmin views for organization oversight.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.organizations.models import Organization

from ._helpers import _build_user_organization_access_rows, _get_active_organization, _is_superadmin_user


@login_required
def superadmin_organizations(request):
    """
    Superadmin-only view showing all organizations with filtering, search and bulk operations.
    """
    if not _is_superadmin_user(request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("Bu bölməyə yalnız superadminlər daxil ola bilər.")

    if request.method == "POST":
        organization = get_object_or_404(Organization, id=request.POST.get("organization_id"))
        action = request.POST.get("action")
        reason = (request.POST.get("reason") or "").strip()

        if action == "suspend":
            organization.status = "suspended"
            organization.is_active = False
            organization.suspended_at = timezone.now()
            organization.suspension_reason = reason
            organization.save(
                update_fields=[
                    "status",
                    "is_active",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_suspended")
                % {"organization_name": organization.name},
            )
        elif action == "unsuspend":
            organization.status = "active"
            organization.is_active = True
            organization.suspended_at = None
            organization.suspension_reason = ""
            organization.save(
                update_fields=[
                    "status",
                    "is_active",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_unsuspended")
                % {"organization_name": organization.name},
            )
        else:
            messages.error(request, pgettext_lazy("accounts.superadmin_orgs.message", "unknown_action"))

        return redirect("accounts:superadmin_organizations")

    search_query = request.GET.get("search", "").strip()
    org_type_filter = request.GET.get("org_type", "").strip().lower()
    status_filter = request.GET.get("status", "").strip().lower()

    organizations = Organization.objects.all().select_related("owner").order_by("-created_at")

    if search_query:
        from django.db.models import Q

        organizations = organizations.filter(
            Q(name__icontains=search_query)
            | Q(slug__icontains=search_query)
            | Q(organization_identifier__icontains=search_query)
            | Q(license_identifier__icontains=search_query)
            | Q(owner__username__icontains=search_query)
            | Q(owner__email__icontains=search_query)
        )

    if org_type_filter:
        organizations = organizations.filter(org_type=org_type_filter)

    if status_filter == "active":
        organizations = organizations.filter(is_active=True, status="active")
    elif status_filter == "suspended":
        organizations = organizations.filter(is_suspended=True)
    elif status_filter == "inactive":
        organizations = organizations.filter(is_active=False)

    paginator = Paginator(organizations, 20)
    page_number = request.GET.get("page")
    organizations_page = paginator.get_page(page_number)

    context = {
        "organizations": organizations_page,
        "organization_access_rows": _build_user_organization_access_rows(
            request.user,
            active_organization=_get_active_organization(request),
            include_active_superadmin_org=True,
            profile_section="superadmin-organizations",
        ),
        "search_query": search_query,
        "org_type_filter": org_type_filter,
        "status_filter": status_filter,
    }
    return render(request, "accounts/superadmin_organizations.html", context)
