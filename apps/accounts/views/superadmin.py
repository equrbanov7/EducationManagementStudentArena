"""
Superadmin views for organization oversight.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from apps.organizations.models import Organization

from ._helpers import _is_superadmin_user


@login_required
def superadmin_organizations(request):
    """
    Superadmin-only view showing all organizations with filtering, search and bulk operations.
    """
    if not _is_superadmin_user(request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("Bu bölməyə yalnız superadminlər daxil ola bilər.")

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
        "search_query": search_query,
        "org_type_filter": org_type_filter,
        "status_filter": status_filter,
    }
    return render(request, "accounts/superadmin_organizations.html", context)
