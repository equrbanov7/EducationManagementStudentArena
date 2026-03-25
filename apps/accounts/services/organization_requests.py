"""
Organization-request services for accounts.
"""

import logging

from django.utils import timezone

from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from core.constants import OrganizationType

from ..models import ProfileRole
from ..queries import pending_student_request_queryset

logger = logging.getLogger(__name__)


def set_student_org_request_status(*, request_obj, status, note="", responded_by=None, when=None):
    """Persist a status update for a student organization request."""
    responded_at = when or timezone.now()
    request_obj.status = status
    request_obj.resolution_note = (note or "").strip()
    request_obj.responded_by = responded_by
    request_obj.responded_at = responded_at
    request_obj.save(
        update_fields=[
            "status",
            "resolution_note",
            "responded_by",
            "responded_at",
            "updated_at",
        ]
    )


def sync_profile_pending_request_snapshot(profile):
    """
    Keep the legacy profile.requested_organization* fields synchronized with the
    latest pending request so older UI sections still render the current state.
    """
    latest_pending_request = (
        pending_student_request_queryset(
            user=profile.user,
            statuses=[StudentOrganizationRequestStatus.PENDING],
        )
        .filter(
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization")
        .order_by("-created_at")
        .first()
    )

    if latest_pending_request:
        next_requested_org = latest_pending_request.organization
        next_requested_name = latest_pending_request.organization.name
        next_requested_message = (latest_pending_request.message or "").strip()
    else:
        next_requested_org = None
        next_requested_name = ""
        next_requested_message = ""

    changed_fields = []
    if profile.requested_organization_id != getattr(next_requested_org, "id", None):
        profile.requested_organization = next_requested_org
        changed_fields.append("requested_organization")
    if profile.requested_organization_name != next_requested_name:
        profile.requested_organization_name = next_requested_name
        changed_fields.append("requested_organization_name")
    if profile.requested_organization_message != next_requested_message:
        profile.requested_organization_message = next_requested_message
        changed_fields.append("requested_organization_message")

    if changed_fields:
        profile.save(update_fields=changed_fields + ["updated_at"])

    return latest_pending_request


def close_other_pending_student_requests(*, user, accepted_organization, responded_by=None, note=""):
    """Auto-close other pending organization requests after one has been accepted."""
    close_note = (note or "").strip() or f"İstifadəçi artıq {accepted_organization.name} təşkilatının üzvüdür."
    now = timezone.now()
    updated = pending_student_request_queryset(
        user=user,
        statuses=[StudentOrganizationRequestStatus.PENDING],
    ).exclude(organization=accepted_organization)

    return updated.update(
        status=StudentOrganizationRequestStatus.AUTO_CLOSED,
        resolution_note=close_note,
        responded_by=responded_by,
        responded_at=now,
        updated_at=now,
    )


def _notify_org_admins_of_new_request(user, organization, role_type):
    """Send in-app notifications to org admins/owners about a new join request."""
    try:
        from apps.notifications.models import InAppNotification, NotificationType
        from apps.organizations.models import Membership

        role_label = {
            MembershipRequestRoleType.STUDENT: "tələbə",
            MembershipRequestRoleType.TEACHER: "müəllim",
            MembershipRequestRoleType.STAFF: "işçi",
        }.get(role_type, "üzv")

        admin_user_ids = list(
            Membership.objects.filter(
                organization=organization,
                is_active=True,
                role__in=["org_owner", "org_admin", "hr"],
            ).values_list("user_id", flat=True)
        )
        # Also include org.owner
        if organization.owner_id and organization.owner_id not in admin_user_ids:
            admin_user_ids.append(organization.owner_id)

        title = f"Yeni {role_label} müraciəti: {user.get_full_name() or user.username}"
        message = (
            f"{user.get_full_name() or user.username} ({user.email}) "
            f"{organization.name} təşkilatına {role_label} kimi qoşulmaq üçün müraciət etdi."
        )
        from django.urls import reverse

        link = reverse("accounts:student_organization_management")

        notifications = [
            InAppNotification(
                recipient_id=admin_id,
                title=title,
                message=message,
                link=link,
                notification_type=NotificationType.APPROVAL,
            )
            for admin_id in admin_user_ids
        ]
        if notifications:
            InAppNotification.objects.bulk_create(notifications, ignore_conflicts=True)
    except Exception:
        logger.exception(
            "Failed to send join-request notifications for user %s to org %s",
            user.pk,
            organization.pk,
        )


def activate_verified_student_membership(user):
    """Back-compat alias for activate_verified_membership (students only)."""
    return activate_verified_membership(user)


def activate_verified_membership(user):
    """
    Finalize pending join requests after email verification.

    For students, teachers, and staff who registered with a join mode and
    selected an organization, this function creates (or updates) the
    ``StudentOrganizationRequest`` record so that org admins can act on it.

    The user is NOT immediately added as a member; that requires explicit
    admin approval.
    """
    profile = getattr(user, "profile", None)
    if profile is None:
        return None

    requested_organization = getattr(profile, "requested_organization", None)
    if requested_organization is None:
        return None

    if profile.organization_id:
        return profile.organization
    if requested_organization.is_suspended:
        return None

    # Determine the request role type based on the profile role.
    if profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        role_type = MembershipRequestRoleType.STUDENT
    elif profile.role == ProfileRole.TEACHER:
        role_type = MembershipRequestRoleType.TEACHER
    else:
        # Staff / HR / member → treat as staff request
        role_type = MembershipRequestRoleType.STAFF

    request_message = (profile.requested_organization_message or "").strip()

    existing_pending = (
        pending_student_request_queryset(
            user=user,
            organization=requested_organization,
            statuses=[StudentOrganizationRequestStatus.PENDING],
        )
        .filter(role_type=role_type)
        .order_by("-created_at")
        .first()
    )
    if existing_pending:
        if existing_pending.message != request_message:
            existing_pending.message = request_message
            existing_pending.save(update_fields=["message", "updated_at"])
    else:
        StudentOrganizationRequest.objects.create(
            user=user,
            organization=requested_organization,
            role_type=role_type,
            message=request_message,
            status=StudentOrganizationRequestStatus.PENDING,
        )
        # Notify org admins of the new request.
        _notify_org_admins_of_new_request(user, requested_organization, role_type)

    profile.requested_organization_name = requested_organization.name
    profile.student_university_name = requested_organization.name
    if requested_organization.org_type == OrganizationType.SCHOOL:
        profile.student_school_identifier = (
            requested_organization.organization_identifier or requested_organization.license_identifier or ""
        )
    else:
        profile.student_school_identifier = ""
    profile.save(
        update_fields=[
            "requested_organization_name",
            "student_university_name",
            "student_school_identifier",
        ]
    )
    sync_profile_pending_request_snapshot(profile)

    return None


__all__ = [
    "activate_verified_membership",
    "activate_verified_student_membership",
    "close_other_pending_student_requests",
    "set_student_org_request_status",
    "sync_profile_pending_request_snapshot",
]
