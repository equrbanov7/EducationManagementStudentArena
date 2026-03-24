"""
Tenant isolation services for organization-scoped queries.
All business logic that needs org-scoping should use these utilities.
"""

from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.accounts.models import ProfileRole
from core.constants import ROLE_LEVELS
from core.utils import get_client_ip

User = get_user_model()


def get_active_memberships(user, organization=None):
    """
    Return active memberships for ``user``.

    Authorization must resolve from memberships only; legacy profile fields are
    intentionally excluded from this helper.
    """
    from apps.organizations.models import Membership

    if not user or not getattr(user, "is_authenticated", False):
        return Membership.objects.none()

    queryset = (
        Membership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
        )
        .select_related("organization", "role", "scope_unit")
        .order_by("-is_primary", "-role__level", "id")
    )
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset


def _membership_role_aliases(user, membership, organization=None):
    role = getattr(membership, "role", None)
    org = organization or getattr(membership, "organization", None)
    is_org_owner = bool(org and getattr(org, "owner_id", None) == getattr(user, "id", None))
    return ProfileRole.aliases_for_membership_role(
        getattr(role, "name", ""),
        level=getattr(role, "level", 0),
        is_org_owner=is_org_owner,
    )


def _membership_effective_level(user, membership, organization=None):
    role = getattr(membership, "role", None)
    role_name = ProfileRole.normalize_membership_role_name(getattr(role, "name", ""))
    aliases = _membership_role_aliases(user, membership, organization=organization)

    candidate_levels = [getattr(role, "level", 0), ROLE_LEVELS.get(role_name, 0)]
    candidate_levels.extend(ROLE_LEVELS.get(alias, 0) for alias in aliases)
    candidate_levels.extend(ProfileRole.LEVELS.get(alias, 0) for alias in aliases)
    return max(candidate_levels, default=0)


def get_membership_role_names(user, organization):
    """Return profile-role aliases implied by the user's active memberships."""
    if not organization:
        return []

    role_names = []
    for membership in get_active_memberships(user, organization):
        for role_name in _membership_role_aliases(user, membership, organization=organization):
            if role_name in ProfileRole.LEVELS and role_name not in role_names:
                role_names.append(role_name)

    role_names.sort(
        key=lambda role_name: (
            ProfileRole.LEVELS.get(role_name, ROLE_LEVELS.get(role_name, 0)),
            role_name,
        ),
        reverse=True,
    )
    return role_names


def user_has_org_role(user, organization, role_names):
    """Return whether ``user`` has any of ``role_names`` in ``organization``."""
    if not organization:
        return False

    normalized = {
        ProfileRole.normalize_membership_role_name(role_name) for role_name in (role_names or []) if role_name
    }
    if not normalized:
        return False

    for membership in get_active_memberships(user, organization):
        if normalized.intersection(_membership_role_aliases(user, membership, organization=organization)):
            return True
    return False


def _candidate_membership_role_names(role_names):
    normalized = {
        ProfileRole.normalize_membership_role_name(role_name) for role_name in (role_names or []) if role_name
    }
    if not normalized:
        return set()

    known_role_names = {
        ProfileRole.MEMBER,
        ProfileRole.STUDENT,
        ProfileRole.LEAD_STUDENT,
        ProfileRole.HR,
        ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER,
        ProfileRole.ORG_ADMIN,
        ProfileRole.ORG_OWNER,
        *ProfileRole.MEMBERSHIP_ROLE_ALIASES.keys(),
        *ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES,
    }

    candidates = set()
    for role_name in known_role_names:
        normalized_role_name = ProfileRole.normalize_membership_role_name(role_name)
        aliases = ProfileRole.aliases_for_membership_role(normalized_role_name)
        if normalized.intersection(aliases):
            candidates.add(normalized_role_name)
    return candidates


def organization_user_queryset(organization, queryset=None):
    """Return active users who belong to ``organization``."""
    base_queryset = queryset if queryset is not None else User.objects.all()
    if organization is None:
        return base_queryset.none()

    return base_queryset.filter(
        memberships__organization=organization,
        memberships__organization__is_active=True,
        memberships__is_active=True,
    ).distinct()


def organization_role_user_queryset(organization, role_names, queryset=None):
    """Return active organization users whose memberships match ``role_names``."""
    base_queryset = organization_user_queryset(organization, queryset=queryset)
    candidate_role_names = _candidate_membership_role_names(role_names)
    if not candidate_role_names:
        return base_queryset.none()

    return base_queryset.filter(
        memberships__organization=organization,
        memberships__organization__is_active=True,
        memberships__is_active=True,
        memberships__role__name__in=candidate_role_names,
    ).distinct()


def get_user_organization(user):
    """Get the user's primary organization from active memberships."""
    membership = get_active_memberships(user).first()
    return membership.organization if membership else None


def tenant_filter(queryset: QuerySet, organization, field_name="organization"):
    """
    Filter a queryset to only include objects belonging to the given organization.
    Returns empty queryset if organization is None.
    """
    if organization is None:
        return queryset.none()
    return queryset.filter(**{field_name: organization})


def get_org_members(organization):
    """Get all active memberships for an organization."""
    from apps.organizations.models import Membership

    if organization is None:
        return Membership.objects.none()

    return (
        Membership.objects.filter(
            organization=organization,
            organization__is_active=True,
            is_active=True,
            user__is_active=True,
        )
        .select_related("user", "role", "organization")
        .order_by("user__username", "-role__level", "id")
    )


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
    levels = [
        _membership_effective_level(user, membership, organization=organization)
        for membership in get_active_memberships(user, organization)
    ]
    return max(levels, default=0)


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
        "resource_id": str(resource_id or ""),
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
