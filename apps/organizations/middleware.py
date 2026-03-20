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
   • 0 active orgs  → attempt legacy materialization once (back-fill the
     membership that the old profile-role system implies), then repeat the
     check.  If that yields exactly 1 org it is auto-selected.
   • 2+ active orgs  → leave ``request.organization = None``.  The user must
     visit the org-picker and make an explicit choice.

3. Once an organization is confirmed, apply
   ``_materialize_legacy_teacher_membership`` *for that specific org only* to
   ensure teacher/assistant-teacher membership records are up to date.
"""


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
        request.org_memberships = []
        request.org_permissions = []

        if not request.user.is_authenticated:
            return self.get_response(request)

        from apps.accounts.views._helpers import _materialize_legacy_teacher_membership
        from .models import Organization

        # ── Step 1: restore org from session ──────────────────────────────
        org_slug = request.session.get("active_organization")
        if org_slug:
            try:
                candidate = Organization.objects.get(slug=org_slug, is_active=True)
            except Organization.DoesNotExist:
                # Org has been deactivated or deleted — purge from session.
                request.session.pop("active_organization", None)
                candidate = None

            if candidate is not None:
                memberships = list(
                    request.user.memberships.filter(organization=candidate, is_active=True)
                    .select_related("role", "scope_unit")
                    .order_by("-is_primary", "-role__level")
                )
                is_superuser = getattr(request.user, "is_superuser", False) or getattr(
                    request.user, "is_superadmin", False
                )
                if memberships or is_superuser:
                    request.organization = candidate
                    request.org_memberships = memberships
                else:
                    # User is no longer a member of the session org — clear it.
                    request.session.pop("active_organization", None)

        # ── Step 2: auto-select when no session org is available ──────────
        if request.organization is None:
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
                # No memberships found — try legacy back-fill *once*.
                _materialize_legacy_teacher_membership(request.user)

                active_memberships = self._fetch_active_memberships(request.user)
                unique_orgs = self._unique_orgs(active_memberships)

                if len(unique_orgs) == 1:
                    request.organization = next(iter(unique_orgs.values()))
                    request.session["active_organization"] = request.organization.slug
                    request.org_memberships = [
                        m for m in active_memberships if m.organization_id == request.organization.id
                    ]
                # len == 0  → leave request.organization = None (no org to assign).
                # Reaching here with 0 orgs after back-fill is a genuine no-org state.

            # len >= 2  → multi-org user; explicit selection required.
            # request.organization stays None; the org-picker view handles this.

        # ── Step 3: finalize permissions for the resolved org ─────────────
        if request.organization:
            # Apply legacy teacher membership materialization scoped to this org.
            request.org_memberships = _materialize_legacy_teacher_membership(
                request.user,
                request.organization,
                memberships=request.org_memberships,
            )

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

        return self.get_response(request)
