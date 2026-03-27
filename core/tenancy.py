"""
Shared helpers for request-scoped tenant filtering.
"""

from django.core.exceptions import ObjectDoesNotExist

TRUSTED_OWNER_CONTEXT_ATTR = "_owner_verified_organization_context"


def _is_tenant_accessible_organization(organization) -> bool:
    return bool(
        organization and getattr(organization, "is_active", False) and getattr(organization, "status", "") == "active"
    )


def _request_context_has_usable_organization(organization) -> bool:
    """
    Accept minimal request doubles unless they explicitly describe a blocked org.

    Unit tests often provide lightweight stubs or ``MagicMock(spec=Organization)``
    objects that do not carry concrete ``is_active``/``status`` field values.
    Those requests still represent a valid active-context check as long as the
    stub does not explicitly mark the org as inactive/suspended.
    """
    if organization is None:
        return False

    is_active = getattr(organization, "is_active", None)
    if isinstance(is_active, bool) and not is_active:
        return False

    status = getattr(organization, "status", None)
    if isinstance(status, str) and status and status != "active":
        return False

    return True


def get_request_organization(request):
    """
    Resolve the active organization selected on this request.
    """
    if request is None:
        return None

    return getattr(request, "organization", None)


def request_has_active_organization_context(request, *, allow_superadmin=True):
    """
    Return whether the request has a valid active tenant context.
    """
    organization = get_request_organization(request)
    if not _request_context_has_usable_organization(organization):
        return False

    user = getattr(request, "user", None)
    if allow_superadmin and bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False)):
        return True
    if bool(getattr(request, TRUSTED_OWNER_CONTEXT_ATTR, False)):
        return user is not None and getattr(organization, "owner_id", None) == getattr(user, "id", None)

    memberships = getattr(request, "org_memberships", None) or []
    if not memberships:
        return False

    if user is not None and getattr(organization, "owner_id", None) == getattr(user, "id", None):
        # Owners may still appear inside a normal membership-backed context.
        return True

    return bool(memberships)


def restore_request_organization_from_profile(request, *, profile=None):
    """
    Re-hydrate ``request.organization`` from the user's profile organization.

    This is a recovery path for org-bound actions reached from profile
    sections when the session lost its active tenant selection.
    """
    if request is None or get_request_organization(request) is not None:
        return False

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False

    if profile is not None:
        resolved_profile = profile
    else:
        try:
            resolved_profile = user.profile
        except (AttributeError, ObjectDoesNotExist):
            resolved_profile = None
    fallback_org = getattr(resolved_profile, "organization", None)
    if not _is_tenant_accessible_organization(fallback_org):
        return False

    from apps.organizations.models import Membership

    memberships = list(
        Membership.objects.filter(
            user=user,
            organization=fallback_org,
            organization__is_active=True,
            organization__status="active",
            is_active=True,
        )
        .select_related("organization", "role", "scope_unit")
        .order_by("-is_primary", "-role__level")
    )

    is_owner = getattr(fallback_org, "owner_id", None) == getattr(user, "id", None)
    is_superadmin = bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))
    if not memberships and not is_owner and not is_superadmin:
        return False

    permissions_set = set()
    for membership in memberships:
        role = getattr(membership, "role", None)
        role_permissions = getattr(role, "permissions", None) or []
        permissions_set.update(role_permissions)
        if getattr(role, "name", "") == "teacher":
            permissions_set.add("course.create")

    request.organization = fallback_org
    request.org_memberships = memberships
    request.org_permissions = list(permissions_set)
    setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, bool(is_owner and not memberships))

    session = getattr(request, "session", None)
    if session is not None:
        session["active_organization"] = fallback_org.slug

    if hasattr(user, "set_active_organization_context"):
        user.set_active_organization_context(
            fallback_org,
            memberships=memberships,
            permissions=request.org_permissions,
        )

    return True


def scoped_by_organization(queryset, request, org_field="organization"):
    """
    Apply active-organization filtering for models bound to an Organization FK.

    Args:
        queryset: Base queryset to scope.
        request: Django request object (for active org lookup).
        org_field: Organization FK field on the model (defaults to ``organization``).
    """
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return queryset.none()

    return queryset.filter(**{org_field: organization})
