"""
User extension methods for organization-related functionality.
These are standalone functions that can be used with any User instance.
"""


def get_organizations(user):
    """
    Get all organizations a user is a member of.

    Args:
        user: Django User instance

    Returns:
        QuerySet of Organization objects
    """
    from apps.organizations.models import Organization

    org_ids = (
        user.memberships.filter(is_active=True)
        .values_list("organization_id", flat=True)
        .distinct()
    )

    return Organization.objects.filter(id__in=org_ids, is_active=True)


def get_memberships(user, organization=None):
    """
    Get user's memberships, optionally filtered by organization.

    Args:
        user: Django User instance
        organization: Optional Organization instance to filter by

    Returns:
        QuerySet of Membership objects
    """
    memberships = user.memberships.filter(is_active=True).select_related(
        "organization", "role", "scope_unit"
    )

    if organization:
        memberships = memberships.filter(organization=organization)

    return memberships


def get_permissions(user, organization):
    """
    Get all permissions for a user in a specific organization.

    Args:
        user: Django User instance
        organization: Organization instance

    Returns:
        List of permission strings
    """
    memberships = get_memberships(user, organization)

    permissions_set = set()
    for membership in memberships:
        if membership.role.permissions:
            permissions_set.update(membership.role.permissions)

    return list(permissions_set)


def get_primary_organization(user):
    """
    Get user's primary organization.

    Args:
        user: Django User instance

    Returns:
        Organization instance or None
    """
    primary_membership = (
        user.memberships.filter(is_active=True, is_primary=True)
        .select_related("organization")
        .first()
    )

    if primary_membership:
        return primary_membership.organization

    # If no primary, return first active membership's organization
    first_membership = (
        user.memberships.filter(is_active=True)
        .select_related("organization")
        .order_by("-role__level")
        .first()
    )

    return first_membership.organization if first_membership else None


def has_org_permission(user, organization, permission):
    """
    Check if user has a specific permission in an organization.

    Args:
        user: Django User instance
        organization: Organization instance
        permission: Permission string to check

    Returns:
        Boolean
    """
    from apps.organizations.permissions import has_permission

    user_permissions = get_permissions(user, organization)
    return has_permission(user_permissions, permission)


def get_max_role_level(user, organization):
    """
    Get user's maximum role level in an organization.

    Args:
        user: Django User instance
        organization: Organization instance

    Returns:
        Integer role level (0 if no memberships)
    """
    memberships = get_memberships(user, organization)

    if not memberships:
        return 0

    return max([m.role.level for m in memberships], default=0)


def can_manage_user(user, target_user, organization):
    """
    Check if user can manage another user in an organization.

    Args:
        user: Django User instance (manager)
        target_user: Django User instance (target)
        organization: Organization instance

    Returns:
        Boolean
    """
    user_level = get_max_role_level(user, organization)
    target_level = get_max_role_level(target_user, organization)

    return user_level > target_level
