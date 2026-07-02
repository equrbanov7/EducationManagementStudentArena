"""
Registration and bootstrap services for accounts.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.notifications.public import notify_org_admins_of_new_request, notify_org_owner_pending_approval
from core.constants import OrganizationType
from core.rls import bypass_rls

from ..models import ProfileRole, UserProfile
from ..policies import map_signup_role_to_profile_role, resolve_membership_role

logger = logging.getLogger(__name__)

User = get_user_model()


def purge_stale_pending_registration(username: str, email: str) -> None:
    """Delete any unverified (is_active=False) users with the given username or email.

    This is called before a new registration attempt so that a user who started
    registration but never completed OTP verification does not permanently block
    the same credentials from being reused.

    Only users who have at least one EmailOTP record are removed — this
    distinguishes mid-registration pending accounts from users that were
    intentionally deactivated by an admin.

    Owned organizations are deleted first to satisfy the ``PROTECT`` constraint
    on ``Organization.owner``.
    """
    from apps.organizations.models import Organization

    if not username and not email:
        return

    stale_users = (
        User.objects.filter(
            Q(username=username) | Q(email=email),
            is_active=False,
        )
        .filter(email_otps__isnull=False)
        .distinct()
    )

    for stale in stale_users:
        logger.info(
            "Purging stale pending registration for user pk=%s username=%s email=[REDACTED]",
            stale.pk,
            stale.username,
        )
        # Remove owned organizations before deleting the user to satisfy PROTECT.
        Organization.objects.filter(owner=stale).delete()
        stale.delete()


@transaction.atomic
def create_user_with_organization(
    username,
    email,
    password,
    first_name,
    last_name,
    signup_mode,
    organization_type,
    country_code,
    country_name,
    password_is_hashed=False,
    join_organization=None,
    institution_not_listed_name="",
    organization_identifier="",
    organization_license_identifier="",
    initial_role=ProfileRole.MEMBER,
    phone="",
    specialization="",
    group_number="",
    department="",
    staff_position="",
    create_join_request=True,
):
    """Create a user, profile, request, and optional organization membership."""
    del country_code

    from apps.organizations.models import Membership, Organization, Role

    with bypass_rls():
        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=False,
        )
        if password_is_hashed:
            user.password = password
            user.save(update_fields=["password"])
        else:
            user.set_password(password)
            user.save()

        organization = None
        requested_organization = None
        requested_organization_name = ""
        resolved_identifier = organization_identifier

        if signup_mode == "individual":
            owner_display_name = (f"{first_name} {last_name}").strip() or username
            organization_name = f"{owner_display_name} Workspace"
            organization = Organization.objects.create(
                name=organization_name,
                org_type=OrganizationType.INDIVIDUAL,
                country=country_name,
                owner=user,
                status="active",
                is_active=True,
            )
            requested_organization = organization
            requested_organization_name = organization.name
        elif signup_mode == "organization_create":
            organization_name = institution_not_listed_name
            requested_organization_name = organization_name
            resolved_identifier = organization_identifier
            # New organizations require superadmin approval before becoming active.
            organization = Organization.objects.create(
                name=organization_name,
                org_type=organization_type,
                country=country_name,
                owner=user,
                status="pending",
                is_active=True,
                organization_identifier=resolved_identifier,
                license_identifier=organization_license_identifier,
            )
            requested_organization = organization
            requested_organization_name = organization.name

            # Notify all superadmins that a new organization is awaiting approval.
            # Import deferred to avoid circular imports at module load time.
            try:
                from apps.accounts.views.superadmin import _notify_superadmins_of_pending_org

                _notify_superadmins_of_pending_org(organization)
            except Exception:
                logger.exception("Failed to notify superadmins about new pending org %s", organization.pk)
            try:
                notify_org_owner_pending_approval(organization=organization)
            except Exception:
                logger.exception("Failed to notify owner about pending org %s", organization.pk)
        else:
            # student_join / teacher_join / staff_join
            requested_organization = join_organization
            requested_organization_name = join_organization.name if join_organization else ""
            resolved_identifier = (
                join_organization.organization_identifier if join_organization else organization_identifier
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.organization_type = organization.org_type if organization is not None else organization_type
        profile.organization = organization
        profile.requested_organization = requested_organization
        profile.requested_organization_name = requested_organization_name
        profile.requested_organization_message = ""
        profile.country = country_name
        profile.role = map_signup_role_to_profile_role(initial_role)
        profile.student_university_name = (
            requested_organization_name
            if signup_mode in {"student_join", "teacher_join", "staff_join"}
            or organization_type
            in {
                OrganizationType.UNIVERSITY,
                OrganizationType.SCHOOL,
                OrganizationType.COURSE_CENTER,
            }
            else ""
        )
        profile.student_school_identifier = resolved_identifier if organization_type == OrganizationType.SCHOOL else ""

        # Persona-specific profile data
        if phone:
            profile.phone = phone
        if signup_mode == "student_join":
            profile.student_specialization = specialization
            profile.student_group_number = group_number
        if signup_mode in {"teacher_join", "staff_join"}:
            profile.department = department
        if signup_mode == "staff_join":
            profile.staff_position = staff_position

        profile.save()

        if create_join_request and (
            organization is None
            and requested_organization is not None
            and signup_mode in {"student_join", "teacher_join", "staff_join"}
        ):
            if signup_mode == "teacher_join":
                req_role_type = MembershipRequestRoleType.TEACHER
            elif signup_mode == "staff_join":
                req_role_type = MembershipRequestRoleType.STAFF
            else:
                req_role_type = MembershipRequestRoleType.STUDENT

            request_obj, created = StudentOrganizationRequest.objects.update_or_create(
                user=user,
                organization=requested_organization,
                role_type=req_role_type,
                status=StudentOrganizationRequestStatus.PENDING,
                defaults={
                    "message": "",
                    "resolution_note": "",
                    "responded_by": None,
                    "responded_at": None,
                },
            )
            if created:
                try:
                    notify_org_admins_of_new_request(request_obj=request_obj)
                except Exception:
                    logger.exception(
                        "Failed to notify org admins about join request %s during registration",
                        request_obj.pk,
                    )

        if organization is not None:
            membership_role = resolve_membership_role(organization, initial_role)
            if membership_role is None:
                membership_role = Role.objects.create(
                    organization=organization,
                    name="owner",
                    display_name="Owner",
                    level=100,
                    scope_type="organization",
                    permissions=["*"],
                    is_system=False,
                    is_active=True,
                )

            Membership.objects.create(
                user=user,
                organization=organization,
                role=membership_role,
                is_primary=True,
                is_active=True,
                assigned_by=user,
            )

    return user, organization, requested_organization, profile


__all__ = ["create_user_with_organization", "purge_stale_pending_registration"]
