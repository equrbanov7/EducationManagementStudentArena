"""
Notification aggregation service.

This app is intentionally started as a service layer first so future
notification channels (in-app, email, push, websocket) can be added
without coupling UI logic to accounts views.
"""

from apps.accounts.models import ProfileRole
from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from apps.organizations.models import Membership

STUDENT_PENDING_INVITE_TITLE = "__student_pending_invite__"


def build_profile_notification_state(*, user, profile):
    pending_student_invites = (
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

    pending_student_join_requests = []
    pending_student_join_org_name = ""
    pending_student_join_message = ""
    if profile.organization is None and profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
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

        if pending_student_join_requests:
            latest_request = pending_student_join_requests[0]
            pending_student_join_org_name = latest_request.organization.name
            pending_student_join_message = (latest_request.message or "").strip()

    student_can_leave_org = bool(
        profile.organization
        and (
            profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}
            or Membership.objects.filter(
                user=user,
                organization=profile.organization,
                is_active=True,
                role__name="student",
            ).exists()
        )
    )

    unread_count = pending_student_invites.count() + len(pending_student_join_requests)

    return {
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "unread_count": unread_count,
    }
