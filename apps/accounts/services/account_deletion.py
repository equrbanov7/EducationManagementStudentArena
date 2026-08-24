"""
Account deletion service.

Handles soft-delete of user accounts with cascade cleanup
of related data (memberships, course enrollments, notifications, etc.).
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.audit.public import log_action
from core.constants import AuditAction

logger = logging.getLogger(__name__)
User = get_user_model()


class AccountDeletionError(Exception):
    """Raised when account deletion cannot proceed."""


def _is_last_org_admin(user):
    """
    Check if user is the sole active admin/owner for any organization.
    Prevents deletion if removing the user would leave an org without admins.
    """
    from apps.organizations.models import Membership, Organization

    # Only currently active organizations must retain at least one active admin.
    owned_orgs = Organization.objects.filter(
        owner=user,
        is_active=True,
        status="active",
    )
    if owned_orgs.exists():
        return True

    # Check if user is the last active admin in any org
    admin_memberships = Membership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
        organization__status="active",
        role__level__gte=80,
    ).select_related("organization")

    for membership in admin_memberships:
        other_admins = (
            Membership.objects.filter(
                organization=membership.organization,
                is_active=True,
                organization__is_active=True,
                organization__status="active",
                role__level__gte=80,
            )
            .exclude(user=user)
            .exists()
        )
        if not other_admins:
            return True

    return False


def soft_delete_account(user, *, request=None, password=None):
    """
    Soft-delete a user account with cascade cleanup.

    Steps:
    1. Validate user can be deleted (not last org admin)
    2. Optionally verify password
    3. Deactivate all memberships
    4. Remove from student groups
    5. Soft-delete notifications
    6. Mark profile as deleted
    7. Deactivate the Django user account
    8. Log the action

    Args:
        user: The User instance to delete
        request: Optional HTTP request (for audit logging)
        password: Optional password for re-confirmation

    Raises:
        AccountDeletionError: If deletion cannot proceed
    """
    if password and not user.check_password(password):
        raise AccountDeletionError("password_incorrect")

    if _is_last_org_admin(user):
        raise AccountDeletionError("last_org_admin")

    with transaction.atomic():
        now = timezone.now()
        profile = getattr(user, "profile", None)

        # 1. Deactivate all memberships
        from apps.organizations.models import Membership

        Membership.objects.filter(user=user, is_active=True).update(
            is_active=False,
            updated_at=now,
        )

        # 2. Remove from student groups
        from apps.exams.models import StudentGroup

        for group in StudentGroup.objects.filter(students=user):
            group.students.remove(user)
        for group in StudentGroup.objects.filter(teachers=user):
            group.teachers.remove(user)

        # 3. Soft-delete notifications
        from apps.notifications.models import InAppNotification

        InAppNotification.objects.filter(
            recipient=user,
            deleted_at__isnull=True,
        ).update(deleted_at=now)

        # 4. Cancel pending organization requests
        from apps.notifications.models import StudentOrganizationRequest

        StudentOrganizationRequest.objects.filter(
            user=user,
            status="pending",
        ).update(status="cancelled")

        # 5. Mark profile as deleted
        if profile:
            profile.is_deleted = True
            profile.deleted_at = now
            profile.organization = None
            profile.requested_organization = None
            profile.save(
                update_fields=[
                    "is_deleted",
                    "deleted_at",
                    "organization",
                    "requested_organization",
                    "updated_at",
                ]
            )

        # 6. Deactivate the Django user account
        user.is_active = False
        user.save(update_fields=["is_active"])

        # 7. Log the action
        log_action(
            action=AuditAction.DELETE,
            user=user,
            organization=getattr(profile, "organization", None),
            obj=user,
            reason="User self-service account deletion",
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=f"{user.username} ({user.email})",
        )

        logger.info(
            "Account soft-deleted for user %s (pk=%s)",
            user.username,
            user.pk,
        )


def _delete_owned_organizations(user):
    """Remove organizations still owned by the user before a hard delete."""
    from apps.organizations.models import Organization

    owned_organizations = Organization.objects.filter(owner=user)
    if not owned_organizations.exists():
        return

    active_owned_organizations = owned_organizations.filter(
        is_active=True,
        status="active",
    )
    if active_owned_organizations.exists():
        raise AccountDeletionError("last_org_admin")

    owned_organizations.delete()


def restore_account(user, *, request=None):
    """
    Restore a soft-deleted user account.

    Args:
        user: The User instance to restore
        request: Optional HTTP request (for audit logging)
    """
    from ..identity import user_access_is_staged

    if user_access_is_staged(user):
        raise AccountDeletionError("staged_account_activation_forbidden")

    with transaction.atomic():
        profile = getattr(user, "profile", None)

        # Reactivate user
        user.is_active = True
        user.save(update_fields=["is_active"])

        # Clear soft-delete flags on profile
        if profile:
            profile.is_deleted = False
            profile.deleted_at = None
            profile.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

        # Log the action
        log_action(
            action=AuditAction.UPDATE,
            user=user,
            obj=user,
            reason="Account restored by admin",
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=f"{user.username} ({user.email})",
        )

        logger.info(
            "Account restored for user %s (pk=%s)",
            user.username,
            user.pk,
        )


def block_account(user, *, request=None):
    """
    Temporarily block a user account without marking it as deleted.

    This keeps account data intact so a superadmin can later unblock the user.
    """
    if _is_last_org_admin(user):
        raise AccountDeletionError("last_org_admin")

    if not user.is_active:
        return

    user.is_active = False
    user.save(update_fields=["is_active"])

    log_action(
        action=AuditAction.UPDATE,
        user=getattr(request, "user", None) if request else None,
        obj=user,
        reason="Account temporarily blocked by superadmin",
        request=request,
        resource_type="User",
        resource_id=str(user.pk),
        resource_repr=f"{user.username} ({user.email})",
    )

    logger.info(
        "Account temporarily blocked for user %s (pk=%s)",
        user.username,
        user.pk,
    )


def unblock_account(user, *, request=None):
    """
    Restore a temporarily blocked account back to active state.
    """
    from ..identity import user_access_is_staged

    if user_access_is_staged(user):
        raise AccountDeletionError("staged_account_activation_forbidden")
    if user.is_active:
        return

    user.is_active = True
    user.save(update_fields=["is_active"])

    log_action(
        action=AuditAction.UPDATE,
        user=getattr(request, "user", None) if request else None,
        obj=user,
        reason="Account unblocked by superadmin",
        request=request,
        resource_type="User",
        resource_id=str(user.pk),
        resource_repr=f"{user.username} ({user.email})",
    )

    logger.info(
        "Account unblocked for user %s (pk=%s)",
        user.username,
        user.pk,
    )


def hard_delete_account(user, *, request=None):
    """
    Permanently delete a user account from the database.
    Should only be used by superadmins.

    Args:
        user: The User instance to permanently delete
        request: Optional HTTP request (for audit logging)
    """
    username = user.username
    email = user.email
    user_pk = user.pk

    # Log before deletion (since user will be gone)
    log_action(
        action=AuditAction.DELETE,
        user=getattr(request, "user", None) if request else None,
        obj=None,
        reason=f"Permanent account deletion of user {username} ({email})",
        request=request,
        resource_type="User",
        resource_id=str(user_pk),
        resource_repr=f"{username} ({email})",
    )

    try:
        with transaction.atomic():
            _delete_owned_organizations(user)
            user.delete()
    except ProtectedError as exc:
        logger.exception(
            "Hard delete blocked for user %s (pk=%s) due to protected relations",
            username,
            user_pk,
        )
        raise AccountDeletionError("hard_delete_blocked") from exc

    logger.info(
        "Account permanently deleted for user %s (pk=%s)",
        username,
        user_pk,
    )
