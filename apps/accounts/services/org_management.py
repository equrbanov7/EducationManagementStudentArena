"""
Organization-management view services (FAZA 9 refactor).

The ``views._helpers._build_student_org_management_section`` function grew to
~800 lines because it builds the data for FOUR different management views
(students / teachers / staff / organizations) inline.

This module extracts the self-contained pieces. The "organizations" branch is
fully isolated — it runs only when ``organization is None`` and a superadmin
selects the organizations view, and shares no local state with the
student/teacher/staff branches — so it can live here safely and be unit-tested
on its own.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse

from apps.accounts.views._helpers import _append_query_params


def build_superadmin_organizations_view(*, request, section, organization_search,
                                        organization_status_filter, organization_type_filter):
    """Populate *section* with the superadmin "organizations" management view.

    Extracted verbatim from ``_build_student_org_management_section``'s
    ``management_view == "organizations"`` branch. Mutates and returns the
    given *section* dict. Only called for superadmins with no active org.
    """
    from apps.organizations.models import Organization as OrganizationModel

    organization_records = OrganizationModel.objects.select_related("owner").annotate(
        active_member_count=Count("memberships", filter=Q(memberships__is_active=True))
    )
    if organization_search:
        organization_records = organization_records.filter(
            Q(name__icontains=organization_search)
            | Q(slug__icontains=organization_search)
            | Q(organization_identifier__icontains=organization_search)
            | Q(license_identifier__icontains=organization_search)
            | Q(owner__username__icontains=organization_search)
            | Q(owner__email__icontains=organization_search)
        )
    if organization_type_filter:
        organization_records = organization_records.filter(org_type=organization_type_filter)
    if organization_status_filter == "active":
        organization_records = organization_records.filter(is_active=True, status="active")
    elif organization_status_filter == "pending":
        organization_records = organization_records.filter(status="pending")
    elif organization_status_filter == "suspended":
        organization_records = organization_records.filter(status="suspended")
    elif organization_status_filter == "inactive":
        organization_records = organization_records.filter(is_active=False)

    section["organization_records"] = Paginator(
        organization_records.order_by("name"),
        12,
    ).get_page(request.GET.get(section["organizations_page_param"]))
    section["pending_org_count"] = OrganizationModel.objects.filter(status="pending").count()
    section["management_view_options"] = [
        {"value": "students", "label": "Tələbələr", "count": 0},
        {"value": "teachers", "label": "Müəllimlər", "count": 0},
        {"value": "staff", "label": "Staff", "count": 0},
        {
            "value": "organizations",
            "label": "Təşkilatlar",
            "count": section["organization_records"].paginator.count,
        },
    ]
    section["post_next_url"] = _append_query_params(
        reverse("accounts:student_organization_management"),
        management_view="organizations",
        organization_search=organization_search,
        organization_status=organization_status_filter,
        organization_type=organization_type_filter,
    )
    return section
