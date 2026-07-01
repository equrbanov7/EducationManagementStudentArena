"""student-org request section builder."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType
from core.rls import bypass_rls

from ....models import ProfileRole
from ..constants import STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH, STUDENT_PENDING_INVITE_TITLE
from ..formatting import _append_query_params, _query_string
from ..roles_map import (
    _map_org_role_to_profile_role,
    _membership_request_role_label,
    _membership_request_role_type_for_profile_role,
)


def _build_student_org_request_section(*, request, profile):
    from apps.organizations.models import Membership, Organization

    search_query = request.GET.get("student_org_request_search", "")
    org_type_filter = (request.GET.get("student_org_request_type", "") or "").strip().lower()
    request_role_type = _membership_request_role_type_for_profile_role(getattr(profile, "role", ProfileRole.MEMBER))
    request_role_label = _membership_request_role_label(request_role_type)
    request_role_label_lower = str(request_role_label).lower()
    allowed_types = {
        OrganizationType.SCHOOL,
        OrganizationType.UNIVERSITY,
        OrganizationType.COURSE_CENTER,
    }
    if org_type_filter not in allowed_types:
        org_type_filter = ""

    with bypass_rls():
        pending_invites = list(
            Membership.objects.filter(
                user=request.user,
                is_active=False,
                title=STUDENT_PENDING_INVITE_TITLE,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization", "role", "assigned_by")
            .order_by("organization__name")
        )
    pending_invite_org_ids = {inv.organization_id for inv in pending_invites}
    for pending_invite in pending_invites:
        invite_profile_role = _map_org_role_to_profile_role(getattr(pending_invite, "role", None))
        invite_role_type = _membership_request_role_type_for_profile_role(invite_profile_role)
        pending_invite.role_label = _membership_request_role_label(invite_role_type)
        pending_invite.role_label_lower = str(pending_invite.role_label).lower()

    legacy_requested_org = getattr(profile, "requested_organization", None)
    has_matching_pending_request = False
    # If the admin already sent an invite for this org, the pending request
    # was auto-closed. Do not recreate it — the invite section handles this.
    has_invite_for_legacy_org = legacy_requested_org is not None and legacy_requested_org.pk in pending_invite_org_ids
    if legacy_requested_org is not None and not has_invite_for_legacy_org:
        with bypass_rls():
            has_matching_pending_request = StudentOrganizationRequest.objects.filter(
                user=request.user,
                organization=legacy_requested_org,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type=request_role_type,
            ).exists()
    if (
        profile.organization is None
        and legacy_requested_org is not None
        and legacy_requested_org.is_active
        and not legacy_requested_org.is_suspended
        and profile.role
        in {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        and not has_matching_pending_request
        and not has_invite_for_legacy_org
    ):
        with bypass_rls():
            StudentOrganizationRequest.objects.create(
                user=request.user,
                organization=legacy_requested_org,
                role_type=request_role_type,
                message=(profile.requested_organization_message or "").strip(),
                status=StudentOrganizationRequestStatus.PENDING,
            )

    with bypass_rls():
        pending_student_requests = list(
            StudentOrganizationRequest.objects.filter(
                user=request.user,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type=request_role_type,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization")
            .order_by("-created_at")
        )
    # If there's a pending invite for an org, suppress the pending request
    # for the same org so the user sees only the invite accept/reject UI.
    if pending_invite_org_ids:
        pending_student_requests = [
            r for r in pending_student_requests if r.organization_id not in pending_invite_org_ids
        ]

    for pending_request in pending_student_requests:
        pending_request.role_label = request_role_label
        pending_request.role_label_lower = request_role_label_lower

    pending_requested_org = pending_student_requests[0].organization if pending_student_requests else None
    pending_requested_org_name = pending_requested_org.name if pending_requested_org else ""
    pending_request_message = (pending_student_requests[0].message or "").strip() if pending_student_requests else ""
    selected_org_id = (
        str(pending_requested_org.id) if pending_requested_org else str(profile.requested_organization_id or "")
    )
    pending_request_org_ids = {item.organization_id for item in pending_student_requests}

    organizations = Organization.objects.filter(is_active=True, status="active").exclude(
        org_type=OrganizationType.INDIVIDUAL
    )
    if org_type_filter:
        organizations = organizations.filter(org_type=org_type_filter)
    if search_query:
        organizations = organizations.filter(
            Q(name__icontains=search_query)
            | Q(country__icontains=search_query)
            | Q(slug__icontains=search_query)
            | Q(organization_identifier__icontains=search_query)
            | Q(license_identifier__icontains=search_query)
        )
    organizations = organizations.order_by("name")

    page_param = "student_org_request_page"
    page_number = request.GET.get(page_param)
    organizations_page = Paginator(organizations, 12).get_page(page_number)

    return {
        "organizations": organizations_page,
        "search_query": search_query,
        "org_type_filter": org_type_filter,
        "pending_invites": pending_invites,
        "pending_invites_count": len(pending_invites),
        "has_pending_invites": bool(pending_invites),
        "pending_invite_org_ids": pending_invite_org_ids,
        "pending_student_requests": pending_student_requests,
        "pending_student_requests_count": len(pending_student_requests),
        "has_pending_student_requests": bool(pending_student_requests),
        "pending_request_org_ids": pending_request_org_ids,
        "current_organization": profile.organization,
        "pending_requested_organization": pending_requested_org,
        "pending_requested_org_name": pending_requested_org_name,
        "pending_request_message": pending_request_message,
        "selected_org_id": selected_org_id,
        "page_param": page_param,
        "pagination_query": _query_string(
            section="student-organization-request",
            student_org_request_search=search_query,
            student_org_request_type=org_type_filter,
        ),
        "post_next_url": _append_query_params(
            reverse("accounts:student_organization_request"),
            student_org_request_search=search_query,
            student_org_request_type=org_type_filter,
        ),
        "request_message_max_length": STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
        "request_role_type": request_role_type,
        "request_role_label": request_role_label,
        "request_role_label_lower": request_role_label_lower,
    }
