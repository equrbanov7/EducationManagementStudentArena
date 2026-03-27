"""
Integration tests – Organization Context (Middleware).

Verifies the full Request → Middleware → Permission → View → DB flow for
the two remaining required scenarios:

3. A single-org user should get the correct organization context automatically.
4. A multi-org user should be forced to explicitly select an organization
   (``request.organization`` stays ``None``; the org-picker handles it).

The tests invoke ``OrganizationMiddleware`` directly with a minimal request
so they exercise the real middleware logic (including DB lookups) without
needing a live HTTP server.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import ProfileRole
from apps.organizations.middleware import OrganizationMiddleware
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_org(name, slug, owner, org_type=OrganizationType.UNIVERSITY):
    """Create an Organization with default-role signals suppressed."""
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug,
            org_type=org_type,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _make_role(org, name="teacher", level=60, permissions=None):
    return Role.objects.create(
        organization=org,
        name=name,
        display_name=name.title(),
        level=level,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=permissions if permissions is not None else ["course.*"],
        is_active=True,
    )


def _assign(user, org, role, *, is_primary=True):
    return Membership.objects.create(
        user=user,
        organization=org,
        role=role,
        is_primary=is_primary,
        is_active=True,
    )


def _dummy_view(request):
    """Minimal view used as the ``get_response`` callable for the middleware."""
    return HttpResponse("ok")


def _make_request(user):
    """Build a GET request with a real (in-memory) session for the given user."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user
    # Provide a real dict-backed session so the middleware can read/write it.
    request.session = {}
    return request


# ---------------------------------------------------------------------------
# Scenario 3 – single-org user: auto-select organization context
# ---------------------------------------------------------------------------


class SingleOrgAutoContextTest(TestCase):
    """
    A user who belongs to exactly ONE organization must have
    ``request.organization`` automatically populated by the middleware
    without requiring an explicit session value.

    Full flow tested: Request → OrganizationMiddleware → DB (Membership query)
    → ``request.organization`` is set.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="single_org_user",
            email="single@orgtest.com",
            password="testpass123",
        )
        self.org = _make_org("Single Org", "single-org-ctx", self.user)
        role = _make_role(self.org)
        _assign(self.user, self.org, role)

        self.middleware = OrganizationMiddleware(_dummy_view)

    def test_single_org_user_gets_org_context_automatically(self):
        """
        Scenario 3 – After the middleware processes a request for a user with
        exactly one active organization, ``request.organization`` must be set
        to that organization without any explicit session pre-population.
        """
        request = _make_request(self.user)
        # No session org set – the middleware must discover it via DB query.
        self.assertNotIn("active_organization", request.session)

        self.middleware(request)

        self.assertIsNotNone(
            request.organization,
            "Middleware must auto-select the organization for a single-org user",
        )
        self.assertEqual(
            request.organization.pk,
            self.org.pk,
            "The auto-selected organization must be the user's only active org",
        )

    def test_single_org_user_session_is_populated(self):
        """
        After auto-selection the middleware must persist the slug to the session
        so subsequent requests do not need another DB round-trip for discovery.
        """
        request = _make_request(self.user)
        self.middleware(request)

        self.assertEqual(
            request.session.get("active_organization"),
            self.org.slug,
            "Middleware must write the org slug to the session for future requests",
        )

    def test_single_org_user_has_permissions_populated(self):
        """
        After org context is resolved, ``request.org_permissions`` must contain
        the permissions granted by the user's membership role.
        """
        request = _make_request(self.user)
        self.middleware(request)

        self.assertTrue(
            len(request.org_permissions) > 0,
            "request.org_permissions must be non-empty for a user with role permissions",
        )

    def test_single_org_user_has_memberships_populated(self):
        """
        After org context is resolved, ``request.org_memberships`` must contain
        the user's memberships in the auto-selected organization.
        """
        request = _make_request(self.user)
        self.middleware(request)

        self.assertTrue(
            len(request.org_memberships) > 0,
            "request.org_memberships must be non-empty after org context is resolved",
        )
        self.assertEqual(
            request.org_memberships[0].organization_id,
            self.org.pk,
        )


# ---------------------------------------------------------------------------
# Scenario 4 – multi-org user: explicit selection required
# ---------------------------------------------------------------------------


class MultiOrgExplicitSelectionTest(TestCase):
    """
    A user who belongs to TWO or more organizations must NOT have
    ``request.organization`` auto-populated by the middleware.  The user must
    visit the org-picker view and make an explicit choice.

    Full flow tested: Request → OrganizationMiddleware → DB (Membership query)
    → ``request.organization`` remains ``None`` (no auto-select).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="multi_org_user_ctx",
            email="multi@orgtest.com",
            password="testpass123",
        )
        self.org_a = _make_org("Multi Org A", "multi-org-a-ctx", self.user)
        self.org_b = _make_org("Multi Org B", "multi-org-b-ctx", self.user, OrganizationType.SCHOOL)

        role_a = _make_role(self.org_a, name="teacher")
        role_b = _make_role(self.org_b, name="member", level=20, permissions=[])

        _assign(self.user, self.org_a, role_a, is_primary=True)
        _assign(self.user, self.org_b, role_b, is_primary=False)

        self.middleware = OrganizationMiddleware(_dummy_view)

    def test_multi_org_user_has_no_auto_org_context(self):
        """
        Scenario 4 – After the middleware processes a request for a user who
        belongs to multiple organizations, ``request.organization`` must remain
        ``None`` because an explicit selection is required.
        """
        request = _make_request(self.user)

        self.middleware(request)

        self.assertIsNone(
            request.organization,
            "Middleware must NOT auto-select an org for a multi-org user; "
            "explicit selection via the org-picker is required",
        )

    def test_multi_org_user_session_not_populated_without_selection(self):
        """
        Without an explicit org selection the middleware must not write any
        ``active_organization`` slug to the session.
        """
        request = _make_request(self.user)
        self.middleware(request)

        self.assertNotIn(
            "active_organization",
            request.session,
            "Session must not be pre-populated for a multi-org user before explicit selection",
        )

    def test_multi_org_user_can_access_org_after_explicit_selection(self):
        """
        Once a multi-org user explicitly selects an organization (by having its
        slug stored in the session), the middleware must resolve that org and
        set ``request.organization`` correctly.
        """
        request = _make_request(self.user)
        # Simulate the org-picker setting the session value
        request.session["active_organization"] = self.org_a.slug

        self.middleware(request)

        self.assertIsNotNone(
            request.organization,
            "After explicit session selection the middleware must resolve the org",
        )
        self.assertEqual(
            request.organization.slug,
            self.org_a.slug,
            "The resolved org must match the one the user selected",
        )

    def test_multi_org_user_org_permissions_empty_without_selection(self):
        """
        Without an active org context ``request.org_permissions`` must be an
        empty list (no permissions can be derived without a selected org).
        """
        request = _make_request(self.user)
        self.middleware(request)

        self.assertEqual(
            request.org_permissions,
            [],
            "org_permissions must be empty when no org context is active",
        )


class PendingOrgContextTest(TestCase):
    """Pending organizations must never become an active tenant context."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pending_ctx_user",
            email="pending-ctx@example.com",
            password="testpass123",
        )
        self.org = _make_org("Pending Org", "pending-org-ctx", self.user)
        self.org.status = "pending"
        self.org.save(update_fields=["status"])

        role = _make_role(self.org, name="rector", level=100, permissions=["*"])
        _assign(self.user, self.org, role)

        self.middleware = OrganizationMiddleware(_dummy_view)

    def test_pending_org_is_not_auto_selected(self):
        request = _make_request(self.user)

        self.middleware(request)

        self.assertIsNone(request.organization)
        self.assertEqual(request.org_memberships, [])
        self.assertEqual(request.org_permissions, [])
        self.assertNotIn("active_organization", request.session)


class MembershipSourceOfTruthTest(TestCase):
    """Regression guards for membership-only organization context resolution."""

    def setUp(self):
        self.middleware = OrganizationMiddleware(_dummy_view)

    def test_profile_fields_do_not_backfill_org_context_without_membership(self):
        user = User.objects.create_user(
            username="legacy_profile_only_user",
            email="legacy_profile_only@example.com",
            password="testpass123",
        )
        organization = _make_org("Legacy Profile Org", "legacy-profile-org", user)

        profile = user.profile
        profile.organization = organization
        profile.organization_type = organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        request = _make_request(user)
        self.middleware(request)

        self.assertIsNone(request.organization)
        self.assertEqual(request.org_memberships, [])
        self.assertEqual(request.org_permissions, [])
        self.assertNotIn("active_organization", request.session)
        self.assertFalse(
            Membership.objects.filter(user=user, organization=organization, is_active=True).exists(),
            "Runtime middleware must not materialize memberships from legacy profile fields",
        )

    def test_selected_org_context_overrides_stale_profile_role_and_org(self):
        user = User.objects.create_user(
            username="multi_org_membership_source_of_truth",
            email="multi_org_membership_source_of_truth@example.com",
            password="testpass123",
        )
        org_a = _make_org("Source Truth Org A", "source-truth-org-a", user)
        org_b = _make_org("Source Truth Org B", "source-truth-org-b", user, OrganizationType.SCHOOL)

        role_a = _make_role(org_a, name="teacher", level=60, permissions=["course.create"])
        role_b = _make_role(org_b, name="member", level=20, permissions=[])

        _assign(user, org_a, role_a, is_primary=True)
        _assign(user, org_b, role_b, is_primary=False)

        profile = user.profile
        profile.organization = org_a
        profile.organization_type = org_a.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        request = _make_request(user)
        request.session["active_organization"] = org_b.slug
        self.middleware(request)

        self.assertEqual(request.organization, org_b)
        self.assertEqual({membership.organization_id for membership in request.org_memberships}, {org_b.id})
        self.assertFalse(request.user.has_role(ProfileRole.TEACHER))
        self.assertTrue(request.user.has_role(ProfileRole.MEMBER))
        self.assertTrue(request.user.has_role(ProfileRole.ORG_OWNER))
        self.assertEqual(request.user._highest_role_level(), ProfileRole.LEVELS.get(ProfileRole.ORG_OWNER, 90))
        self.assertEqual(
            request.organization.slug,
            org_b.slug,
            "The resolved org must match the one the user selected",
        )
