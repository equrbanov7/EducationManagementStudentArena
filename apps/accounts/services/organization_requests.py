"""
Organization-request services for accounts.
"""

from django.utils import timezone

from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType

from ..models import ProfileRole
from ..queries import pending_student_request_queryset


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


def activate_verified_student_membership(user):
    """
    Keep student join requests pending after email verification.
    Students only become full members after organization approval.
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

    if profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        request_message = (profile.requested_organization_message or "").strip()
        existing_pending = (
            pending_student_request_queryset(
                user=user,
                organization=requested_organization,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            )
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
                message=request_message,
                status=StudentOrganizationRequestStatus.PENDING,
            )

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
    "activate_verified_student_membership",
    "close_other_pending_student_requests",
    "set_student_org_request_status",
    "sync_profile_pending_request_snapshot",
]
