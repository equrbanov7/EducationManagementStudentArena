"""
Tenant isolation services for organization-scoped queries.
All business logic that needs org-scoping should use these utilities.
"""

from uuid import UUID

from django.db.models import QuerySet

from core.utils import get_client_ip


def get_user_organization(user):
    """Get the user's primary organization from their profile."""
    if not user or not user.is_authenticated:
        return None
    profile = getattr(user, "profile", None)
    if profile:
        return profile.organization
    return None


def tenant_filter(queryset: QuerySet, organization, field_name="organization"):
    """
    Filter a queryset to only include objects belonging to the given organization.
    Returns empty queryset if organization is None.
    """
    if organization is None:
        return queryset.none()
    return queryset.filter(**{field_name: organization})


def get_org_members(organization):
    """Get all active members of an organization."""
    if organization is None:
        return []
    from apps.accounts.models import UserProfile

    return UserProfile.objects.filter(organization=organization).select_related("user")


def get_org_roles(organization):
    """Get all active roles for an organization."""
    if organization is None:
        return []
    from apps.organizations.models import Role

    return Role.objects.filter(organization=organization, is_active=True).order_by("-level")


def get_user_org_role_level(user, organization):
    """Get the highest role level a user has in an organization."""
    if not user or not organization:
        return 0
    from apps.organizations.models import Membership

    membership = (
        Membership.objects.filter(user=user, organization=organization, is_active=True)
        .order_by("-role__level")
        .select_related("role")
        .first()
    )
    if membership:
        return membership.role.level
    return 0


def can_user_manage_org(user, organization):
    """Check if user has management-level access to the organization (level >= 80)."""
    return get_user_org_role_level(user, organization) >= 80


def can_user_assign_role(assigner, target_role_level, organization):
    """
    Check if assigner can assign a role of the given level.
    Assigner must have a higher role level than the target role.
    """
    assigner_level = get_user_org_role_level(assigner, organization)
    return assigner_level > target_role_level


def create_audit_log(
    user,
    organization,
    action,
    resource_type="",
    resource_id="",
    resource_repr="",
    old_values=None,
    new_values=None,
    reason="",
    request=None,
):
    """Create an audit log entry."""
    from apps.audit.models import AuditLog

    request_id = None
    if request:
        raw_request_id = (
            getattr(request, "request_id", None)
            or request.META.get("HTTP_X_REQUEST_ID")
            or request.META.get("HTTP_X_CORRELATION_ID")
        )
        if raw_request_id:
            try:
                request_id = UUID(str(raw_request_id))
            except (TypeError, ValueError, AttributeError):
                request_id = None

    kwargs = {
        "user": user,
        "organization": organization,
        "action": action,
        "resource_type": resource_type,
        "resource_id": str(resource_id),
        "resource_repr": resource_repr,
        "old_values": old_values,
        "new_values": new_values,
        "reason": reason,
        "request_id": request_id,
    }
    if request:
        kwargs["ip_address"] = get_client_ip(request)
        kwargs["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]

    return AuditLog.objects.create(**kwargs)
