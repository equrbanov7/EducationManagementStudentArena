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

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.utils.functional import SimpleLazyObject

from core.rls import apply_rls_request_context, bypass_rls, reset_rls_context
from core.roles import ProfileRole
from core.tenancy import TRUSTED_OWNER_CONTEXT_ATTR

from .services import ensure_owner_membership, is_tenant_accessible_organization


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

    # P9 (2026-07-02): org-switcher siyahısının per-user TTL keşi. YALNIZ navbar
    # lazy yolunda istifadə olunur — org-həlli/permission yolları hər zaman canlı
    # sorğu ilə işləyir. Membership dəyişikliyində signal invalidasiyası var
    # (signals.py), TTL yalnız ehtiyat tordur.
    ORG_SWITCHER_CACHE_TTL = 60

    @staticmethod
    def org_switcher_cache_key(user_id):
        return f"ems:org_switcher:v1:{user_id}"

    @classmethod
    def _cached_active_memberships(cls, user):
        """Navbar org-switcher üçün üzvlük siyahısı — 60s keşlə."""
        from django.core.cache import cache

        key = cls.org_switcher_cache_key(user.pk)
        try:
            cached = cache.get(key)
        except Exception:
            cached = None
        if cached is not None:
            return cached
        memberships = cls._fetch_active_memberships(user)
        try:
            cache.set(key, memberships, timeout=cls.ORG_SWITCHER_CACHE_TTL)
        except Exception:
            pass
        return memberships

    @staticmethod
    def _fetch_active_memberships(user):
        """Return all active memberships for *user* across active organizations."""
        with bypass_rls():
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

    @staticmethod
    def _profile_allows_owner_fallback(profile) -> bool:
        return getattr(profile, "role", None) in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}

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

        try:
            if not request.user.is_authenticated:
                return self.get_response(request)

            from .models import Organization

            # ── Step 1: restore org from session ──────────────────────────────
            org_slug = request.session.get("active_organization")
            if org_slug:
                # Single query: join memberships → organization to avoid a
                # separate Organization.objects.get() round-trip.
                with bypass_rls():
                    memberships = list(
                        request.user.memberships.filter(
                            organization__slug=org_slug,
                            organization__is_active=True,
                            is_active=True,
                        )
                        .select_related("organization", "role", "scope_unit")
                        .order_by("-is_primary", "-role__level")
                    )
                is_superuser = getattr(request.user, "is_superuser", False) or getattr(
                    request.user, "is_superadmin", False
                )
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
                    try:
                        profile = request.user.profile
                    except (AttributeError, ObjectDoesNotExist):
                        profile = None
                    owner_org = Organization.objects.filter(
                        slug=org_slug,
                        is_active=True,
                        owner=request.user,
                    ).first()
                    if owner_org is not None:
                        if getattr(owner_org, "status", "") == "active":
                            # An explicitly selected org in the session is a stronger
                            # signal than stale profile role fields. Real org owners
                            # must be able to recover tenant context for that selected
                            # org even when legacy profile data still says "member".
                            owner_membership = ensure_owner_membership(request.user, owner_org)
                            request.organization = owner_org
                            request.org_memberships = [owner_membership] if owner_membership is not None else []
                            setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, owner_membership is None)
                        elif getattr(owner_org, "status", "") != "active":
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
                    try:
                        profile = request.user.profile
                    except (AttributeError, ObjectDoesNotExist):
                        profile = None

                    owner_fallback_org = getattr(profile, "organization", None)
                    if (
                        self._profile_allows_owner_fallback(profile)
                        and owner_fallback_org is not None
                        and getattr(owner_fallback_org, "owner_id", None) == getattr(request.user, "id", None)
                        and is_tenant_accessible_organization(owner_fallback_org)
                    ):
                        owner_membership = ensure_owner_membership(request.user, owner_fallback_org)
                        request.organization = owner_fallback_org
                        request.session["active_organization"] = owner_fallback_org.slug
                        request.org_memberships = [owner_membership] if owner_membership is not None else []
                        setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, owner_membership is None)

                # len >= 2  → multi-org user; explicit selection required.
                # request.organization stays None; the org-picker view handles this.

                # Preserve the full membership list for the context processor so it
                # can build the org-switcher without issuing another query.
                request._all_org_memberships = active_memberships

            else:
                # Session org path: the full org-switcher list (memberships across
                # every org) is consumed ONLY by the navbar context processor on
                # full-page HTML renders. JSON/AJAX endpoints (badges API, section
                # fragments' JSON, DRF, etc.) never read it. Defer the query behind
                # SimpleLazyObject so it runs at most once, and only if something
                # actually accesses ``request._all_org_memberships`` — removing a
                # per-request membership query from every non-navbar response.
                request._all_org_memberships = SimpleLazyObject(lambda: self._cached_active_memberships(request.user))

            # ── Step 3: finalize permissions for the resolved org ─────────────
            if is_tenant_accessible_organization(request.organization):
                permissions_set = set()
                for membership in request.org_memberships:
                    if membership.role.permissions:
                        permissions_set.update(membership.role.permissions)
                # NOTE: the legacy teacher `course.create` back-compat was moved to
                # the data layer (migration organizations.0011) so RBAC stays fully
                # centralised — no role-name special-casing here.
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

            # ── Step 4: propagate tenant context to the PostgreSQL session ────
            # Set the RLS context variables so that database-level Row-Level
            # Security policies can restrict queries to the active organisation.
            # User-scoped policies (for example notification inbox rows) also
            # receive the current authenticated user id.
            # Both ``is_superuser`` (Django's built-in staff/admin flag) and
            # ``is_superadmin`` (a project-level synonym used by profile/auth
            # extensions) represent full cross-tenant administrative access.
            # Neither is a lesser privilege than the other; either flag grants the
            # RLS bypass for operations such as admin reports and management commands.
            # Batched into ONE round-trip (set_config × N in a single SELECT)
            # instead of 2–3 separate statements. Behaviour is identical:
            #  • superuser            → user + bypass ON
            #  • org resolved         → user + bypass OFF + tenant=org
            #  • no org (secure stop) → user + bypass OFF + tenant="" (deny all)
            is_superuser = getattr(request.user, "is_superuser", False) or getattr(request.user, "is_superadmin", False)

            # Faza 2 / Mərhələ 3B: flaq açıq olduqda RLS-i request transaction-ı
            # daxilində SET LOCAL ilə tətbiq edən execute_wrapper qoşulur
            # (PgBouncer transaction-mode təhlükəsiz). Default OFF → mövcud
            # session-scope davranış. Bax: docs/performance/FAZA2_3B_TRANSACTION_POOLING.md.
            if getattr(settings, "RLS_TRANSACTION_SCOPED", False):
                from core.rls_pooling import RLSTransactionGuard

                guard = RLSTransactionGuard(
                    user_id=request.user.pk,
                    org_id=request.organization.pk if request.organization is not None else None,
                    bypass=is_superuser,
                )
                rls_wrapper_cm = connection.execute_wrapper(guard)
                rls_wrapper_cm.__enter__()
                request._rls_wrapper_cm = rls_wrapper_cm
            else:
                apply_rls_request_context(
                    user_id=request.user.pk,
                    org_id=request.organization.pk if request.organization is not None else None,
                    bypass=is_superuser,
                )

            return self.get_response(request)
        finally:
            # ── Cleanup: reset RLS context before connection returns to pool ──
            # This prevents tenant state from leaking into the next request that
            # reuses the same pooled connection, even if the view raises.
            rls_wrapper_cm = getattr(request, "_rls_wrapper_cm", None)
            if rls_wrapper_cm is not None:
                from core.rls_pooling import reset_txn_flags

                try:
                    rls_wrapper_cm.__exit__(None, None, None)
                finally:
                    reset_txn_flags(connection)
            else:
                reset_rls_context(only_if_connection_open=True)
