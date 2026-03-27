"""
Middleware for handling organization context in requests.

Organization resolution order
------------------------------
1. If ``active_organization`` is set in the session, load that org and verify
   the current user has an active membership (or is a super-admin).
   If the org is inactive or the user is no longer a member the
   slug is removed from the session and resolution continues.

2. If no session org is present, query the user's **active** memberships
   without first materializing anything.
   • Exactly 1 active org  → auto-select it and persist the slug to the
     session as a convenience (single-org users must not be forced to pick
     every request).
   • 0 active orgs  → leave ``request.organization = None``.
   • 2+ active orgs  → leave ``request.organization = None``.  The user must
     visit the org-picker and make an explicit choice.
"""

from core.tenancy import TRUSTED_OWNER_CONTEXT_ATTR

from .services import is_tenant_accessible_organization


class OrganizationMiddleware:
    """
    Middleware to set organization context on each request.
    Sets request.organization, request.org_memberships, and request.org_permissions.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_active_memberships(user):
        """Return all active memberships for *user* across active organizations."""
        return list(
            user.memberships.filter(is_active=True, organization__is_active=True)
            .filter(organization__status="active")
            .select_related("organization", "role", "scope_unit")
            .order_by("-is_primary", "-role__level")
        )

    @staticmethod
    def _unique_orgs(memberships):
        """Return an ``{org_id: Organization}`` mapping from a membership list."""
        result = {}
        for m in memberships:
            result.setdefault(m.organization_id, m.organization)
        return result

    # ------------------------------------------------------------------
    # Main entry-point
    # ------------------------------------------------------------------

    def __call__(self, request):
        # Initialize organization-related attributes
        request.organization = None
        request.blocked_organization = None
        request.org_memberships = []
        request.org_permissions = []
        setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, False)
        # All active memberships across every org – used by the context
        # processor to build the org-switcher list without extra DB queries.
        request._all_org_memberships = []

        if not request.user.is_authenticated:
            return self.get_response(request)

        from .models import Organization

        # ── Step 1: restore org from session ──────────────────────────────
        org_slug = request.session.get("active_organization")
        if org_slug:
            # Single query: join memberships → organization to avoid a
            # separate Organization.objects.get() round-trip.
            memberships = list(
                request.user.memberships.filter(
                    organization__slug=org_slug,
                    organization__is_active=True,
                    is_active=True,
                )
                .select_related("organization", "role", "scope_unit")
                .order_by("-is_primary", "-role__level")
            )
            is_superuser = getattr(request.user, "is_superuser", False) or getattr(request.user, "is_superadmin", False)
            if memberships:
                # All memberships share the same organization because the slug
                # column has a UNIQUE constraint — memberships[0].organization
                # is always the correct org object.
                session_org = memberships[0].organization
                if getattr(session_org, "status", "") == "active":
                    request.organization = session_org
                    request.org_memberships = memberships
                else:
                    request.blocked_organization = session_org
            elif is_superuser:
                # Superusers may have no membership rows; fall back to a
                # direct org lookup so they can still access the org.
                try:
                    session_org = Organization.objects.get(slug=org_slug, is_active=True)
                    if getattr(session_org, "status", "") == "active":
                        request.organization = session_org
                        request.org_memberships = []
                    else:
                        request.blocked_organization = session_org
                except Organization.DoesNotExist:
                    request.session.pop("active_organization", None)
            else:
                owner_org = Organization.objects.filter(
                    slug=org_slug,
                    is_active=True,
                    owner=request.user,
                ).first()
                if owner_org is not None:
                    if getattr(owner_org, "status", "") == "active":
                        request.organization = owner_org
                        request.org_memberships = []
                        setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, True)
                    else:
                        request.blocked_organization = owner_org
                else:
                    # User is no longer a member of the session org — clear it.
                    request.session.pop("active_organization", None)

        # ── Step 2: auto-select when no session org is available ──────────
        if request.organization is None and request.blocked_organization is None:
            active_memberships = self._fetch_active_memberships(request.user)
            unique_orgs = self._unique_orgs(active_memberships)

            if len(unique_orgs) == 1:
                # Single org — auto-select for convenience.
                request.organization = next(iter(unique_orgs.values()))
                request.session["active_organization"] = request.organization.slug
                request.org_memberships = [
                    m for m in active_memberships if m.organization_id == request.organization.id
                ]

            elif len(unique_orgs) == 0:
                # No active memberships: deny by default until an organization
                # context can be established via real membership data.
                pass

            # len >= 2  → multi-org user; explicit selection required.
            # request.organization stays None; the org-picker view handles this.

            # Preserve the full membership list for the context processor so it
            # can build the org-switcher without issuing another query.
            request._all_org_memberships = active_memberships

        else:
            # Session org path: fetch all memberships for the org-switcher list
            # only if the user belongs to more than one org.  Re-use the already
            # fetched current-org memberships as a starting point; a second query
            # is issued only when there are known multiple orgs (rare case).
            request._all_org_memberships = self._fetch_active_memberships(request.user)

        # ── Step 3: finalize permissions for the resolved org ─────────────
        if is_tenant_accessible_organization(request.organization):
            permissions_set = set()
            for membership in request.org_memberships:
                if membership.role.permissions:
                    permissions_set.update(membership.role.permissions)
                if getattr(membership.role, "name", "") == "teacher":
                    # Back-compat: older default teacher roles missed course.create
                    # even though the UI and flow allow teachers to create courses.
                    permissions_set.add("course.create")
            request.org_permissions = list(permissions_set)
        elif request.organization is not None:
            request.organization = None
            request.org_memberships = []
            request.org_permissions = []
            request.session.pop("active_organization", None)

        if hasattr(request.user, "set_active_organization_context"):
            request.user.set_active_organization_context(
                request.organization,
                memberships=request.org_memberships,
                permissions=request.org_permissions,
            )

        return self.get_response(request)
