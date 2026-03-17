"""
Middleware for handling organization context in requests.
"""


class OrganizationMiddleware:
    """
    Middleware to set organization context on each request.
    Sets request.organization, request.org_memberships, and request.org_permissions.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Initialize organization-related attributes
        request.organization = None
        request.org_memberships = []
        request.org_permissions = []

        # Only process for authenticated users
        if request.user.is_authenticated:
            from apps.accounts.views._helpers import _materialize_legacy_teacher_membership
            from .models import Organization

            # Get organization from session (set by organization selector)
            org_slug = request.session.get("active_organization")

            if org_slug:
                # Try to load the organization
                try:
                    request.organization = Organization.objects.get(slug=org_slug, is_active=True)
                except Organization.DoesNotExist:
                    # Organization not found or inactive, clear session
                    request.session.pop("active_organization", None)

            # If organization is set, load memberships and permissions
            if request.organization:
                # Get active memberships for this user in this organization
                request.org_memberships = list(
                    request.user.memberships.filter(organization=request.organization, is_active=True)
                    .select_related("role", "scope_unit")
                    .order_by("-is_primary", "-role__level")
                )

                can_bootstrap_admin_membership = False
                if not request.org_memberships:
                    from apps.accounts.models import ProfileRole

                    profile = getattr(request.user, "profile", None)
                    can_bootstrap_admin_membership = (
                        getattr(profile, "organization_id", None) == request.organization.id
                        and getattr(profile, "role", None) in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}
                    )

                if not request.org_memberships and not can_bootstrap_admin_membership and not (
                    getattr(request.user, "is_superuser", False) or getattr(request.user, "is_superadmin", False)
                ):
                    request.organization = None
                    request.session.pop("active_organization", None)

            if request.organization is None:
                # Backfill legacy teacher membership before querying so that new/legacy
                # users without explicit membership records are found in the query below.
                _materialize_legacy_teacher_membership(request.user)

                active_memberships = list(
                    request.user.memberships.filter(is_active=True, organization__is_active=True)
                    .select_related("organization", "role", "scope_unit")
                    .order_by("-is_primary", "-role__level")
                )
                unique_organizations = {}
                for membership in active_memberships:
                    unique_organizations.setdefault(membership.organization_id, membership.organization)

                if len(unique_organizations) == 1:
                    request.organization = next(iter(unique_organizations.values()))
                    request.session["active_organization"] = request.organization.slug
                    request.org_memberships = [
                        membership
                        for membership in active_memberships
                        if membership.organization_id == request.organization.id
                    ]

            if request.organization:
                request.org_memberships = _materialize_legacy_teacher_membership(
                    request.user,
                    request.organization,
                    memberships=request.org_memberships,
                )

                # Collect all permissions from memberships
                permissions_set = set()
                for membership in request.org_memberships:
                    if membership.role.permissions:
                        permissions_set.update(membership.role.permissions)

                request.org_permissions = list(permissions_set)

            if hasattr(request.user, "set_active_organization_context"):
                request.user.set_active_organization_context(
                    request.organization,
                    memberships=request.org_memberships,
                    permissions=request.org_permissions,
                )

        response = self.get_response(request)
        return response
