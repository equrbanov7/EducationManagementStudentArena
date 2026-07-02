"""
Profile notification state aggregator.

Builds the notification-related context block for the user profile page
(pending invites, pending join requests, leave eligibility, unread count).
"""

from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.organizations.models import Membership
from core.rls import bypass_rls
from core.roles import ProfileRole, map_org_role_to_profile_role

from .constants import STUDENT_PENDING_INVITE_TITLE
from .events import notify_org_owner_pending_approval
from .helpers import get_membership_request_role_label


def build_profile_notification_state(*, user, profile):
    if (
        profile.organization is not None
        and getattr(profile.organization, "owner_id", None) == getattr(user, "id", None)
        and getattr(profile.organization, "is_active", False)
        and getattr(profile.organization, "status", "") == "pending"
    ):
        notify_org_owner_pending_approval(organization=profile.organization)

    pending_student_invites = list(
        Membership.objects.filter(
            user=user,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization", "assigned_by", "role")
        .order_by("organization__name")
    )
    for pending_invite in pending_student_invites:
        invite_role_name = getattr(getattr(pending_invite, "role", None), "name", "")
        if invite_role_name in {
            "teacher",
            "instructor",
            "professor",
            "associate_professor",
            "assistant_teacher",
            "assistant",
        }:
            pending_invite.role_label = get_membership_request_role_label(MembershipRequestRoleType.TEACHER)
        elif invite_role_name == "student":
            pending_invite.role_label = get_membership_request_role_label(MembershipRequestRoleType.STUDENT)
        else:
            pending_invite.role_label = get_membership_request_role_label(MembershipRequestRoleType.STAFF)
        pending_invite.role_label_lower = str(pending_invite.role_label).lower()

    pending_student_join_requests = []
    pending_student_join_org_name = ""
    pending_student_join_message = ""
    if profile.organization is None:
        with bypass_rls():
            pending_student_join_requests = list(
                StudentOrganizationRequest.objects.filter(
                    user=user,
                    status=StudentOrganizationRequestStatus.PENDING,
                    organization__is_active=True,
                    organization__status="active",
                )
                .select_related("organization")
                .order_by("-created_at")
            )

        for pending_request in pending_student_join_requests:
            pending_request.role_label = get_membership_request_role_label(pending_request.role_type)
            pending_request.role_label_lower = str(pending_request.role_label).lower()
            pending_request.can_cancel = True

        if pending_student_join_requests:
            latest_request = pending_student_join_requests[0]
            pending_student_join_org_name = latest_request.organization.name
            pending_student_join_message = (latest_request.message or "").strip()

    active_membership = None
    membership_profile_role = None
    if profile.organization:
        active_membership = (
            Membership.objects.filter(
                user=user,
                organization=profile.organization,
                is_active=True,
            )
            .select_related("role")
            .order_by("-is_primary", "-role__level")
            .first()
        )
        membership_profile_role = map_org_role_to_profile_role(getattr(active_membership, "role", None))

    student_can_leave_org = bool(
        profile.organization
        and getattr(profile.organization, "owner_id", None) != user.id
        and (
            membership_profile_role
            in {
                ProfileRole.STUDENT,
                ProfileRole.LEAD_STUDENT,
                ProfileRole.TEACHER,
                ProfileRole.ASSISTANT_TEACHER,
                ProfileRole.MEMBER,
                ProfileRole.HR,
            }
            or (
                active_membership is None
                and profile.role
                in {
                    ProfileRole.STUDENT,
                    ProfileRole.LEAD_STUDENT,
                    ProfileRole.TEACHER,
                    ProfileRole.ASSISTANT_TEACHER,
                    ProfileRole.MEMBER,
                    ProfileRole.HR,
                }
            )
        )
    )

    unread_count = len(pending_student_invites) + len(pending_student_join_requests)

    return {
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "unread_count": unread_count,
    }
