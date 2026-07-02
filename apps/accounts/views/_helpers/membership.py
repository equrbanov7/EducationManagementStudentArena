"""
Membership helpers.

Synchronize a user's role memberships within an organization, backfill admin
memberships, and wrap the pending student-organization-request services.
"""

from ...models import ProfileRole
from ...queries import pending_student_request_queryset
from ...services import (
    activate_verified_student_membership,
    close_other_pending_student_requests,
    set_student_org_request_status,
    sync_profile_pending_request_snapshot,
)
from .rbac import _is_superadmin_user
from .roles_map import _map_org_role_to_profile_role, _resolve_membership_role
from .tenant import _bind_active_role_context


def _pending_student_request_queryset(*, user=None, organization=None, statuses=None):
    return pending_student_request_queryset(user=user, organization=organization, statuses=statuses)


def _set_student_org_request_status(
    *,
    request_obj,
    status,
    note="",
    responded_by=None,
    when=None,
):
    return set_student_org_request_status(
        request_obj=request_obj,
        status=status,
        note=note,
        responded_by=responded_by,
        when=when,
    )


def _sync_profile_pending_request_snapshot(profile):
    return sync_profile_pending_request_snapshot(profile)


def _close_other_pending_student_requests(*, user, accepted_organization, responded_by=None, note=""):
    return close_other_pending_student_requests(
        user=user,
        accepted_organization=accepted_organization,
        responded_by=responded_by,
        note=note,
    )


def _activate_verified_student_membership(user):
    return activate_verified_student_membership(user)


def _sync_user_role_memberships(user, organization, desired_role_names, *, actor=None, editable_role_names=None):
    from apps.organizations.models import Membership

    if organization is None:
        return []

    from .constants import PROFILE_ROLE_NAMES

    desired = set(desired_role_names or []) & PROFILE_ROLE_NAMES
    editable = set(editable_role_names or PROFILE_ROLE_NAMES) & PROFILE_ROLE_NAMES
    editable -= {ProfileRole.SUPERADMIN, ProfileRole.ORG_OWNER}

    desired_membership_roles = {}
    for role_name in sorted(desired & editable, key=lambda item: ProfileRole.LEVELS.get(item, 0), reverse=True):
        membership_role = _resolve_membership_role(organization, role_name)
        if membership_role is not None:
            desired_membership_roles[membership_role.id] = membership_role

    current_memberships = list(
        Membership.objects.filter(user=user, organization=organization)
        .select_related("role")
        .order_by("-is_active", "-is_primary", "-role__level")
    )

    memberships_to_deactivate = []
    for membership in current_memberships:
        mapped_role = _map_org_role_to_profile_role(membership.role)
        if mapped_role in editable and membership.role_id not in desired_membership_roles and membership.is_active:
            memberships_to_deactivate.append(membership.id)

    if memberships_to_deactivate:
        Membership.objects.filter(id__in=memberships_to_deactivate).update(is_active=False, is_primary=False)

    for membership_role in desired_membership_roles.values():
        Membership.objects.update_or_create(
            user=user,
            organization=organization,
            role=membership_role,
            scope_unit=None,
            defaults={
                "is_active": True,
                "is_primary": False,
                "assigned_by": actor,
            },
        )

    final_memberships = list(
        Membership.objects.filter(user=user, organization=organization, is_active=True)
        .select_related("role")
        .order_by("-role__level", "-is_primary", "id")
    )
    Membership.objects.filter(user=user, organization=organization, is_primary=True).update(is_primary=False)
    if final_memberships:
        primary_membership = final_memberships[0]
        primary_membership.is_primary = True
        primary_membership.save(update_fields=["is_primary"])
        final_memberships[0] = primary_membership

    _bind_active_role_context(user, organization, memberships=final_memberships)
    return final_memberships


def _ensure_profile_admin_membership(user, organization):
    """
    Backfill membership for org owner/admin profiles that are missing organization membership.
    This prevents false-negative `role.assign` errors for valid tenant admins.
    """
    from apps.organizations.models import Membership
    from apps.organizations.public import ensure_owner_membership

    if _is_superadmin_user(user):
        return

    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", None)
    profile_org = getattr(profile, "organization", None)
    is_org_owner = bool(organization and getattr(organization, "owner_id", None) == getattr(user, "id", None))

    if not is_org_owner and profile_role not in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}:
        return
    if not organization or profile_org != organization:
        return
    if Membership.objects.filter(user=user, organization=organization, is_active=True).exists():
        return
    ensure_owner_membership(user, organization)
