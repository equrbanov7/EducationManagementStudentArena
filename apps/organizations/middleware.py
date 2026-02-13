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
            # Get organization from session (set by organization selector)
            org_slug = request.session.get("active_organization")

            if org_slug:
                # Try to load the organization
                from .models import Organization

                try:
                    request.organization = Organization.objects.get(
                        slug=org_slug, is_active=True
                    )
                except Organization.DoesNotExist:
                    # Organization not found or inactive, clear session
                    request.session.pop("active_organization", None)

            # If organization is set, load memberships and permissions
            if request.organization:
                # Get active memberships for this user in this organization
                request.org_memberships = list(
                    request.user.memberships.filter(
                        organization=request.organization, is_active=True
                    )
                    .select_related("role", "scope_unit")
                    .order_by("-is_primary", "-role__level")
                )

                # Collect all permissions from memberships
                permissions_set = set()
                for membership in request.org_memberships:
                    if membership.role.permissions:
                        permissions_set.update(membership.role.permissions)

                request.org_permissions = list(permissions_set)

        response = self.get_response(request)
        return response
