"""
Tests for PermissionRequiredMixin and LevelRequiredMixin dispatch behavior.

Verifies that:
- dispatch() executes exactly once per request (no double-dispatch).
- Unauthenticated requests are redirected before the view body runs.
- Requests without an active organization are redirected before the view body runs.
- Requests lacking the required permission receive 403 before the view body runs.
- Requests lacking the required level receive 403 before the view body runs.
- Authorized requests reach the view body exactly once.
"""

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.views import View

from core.constants import OrganizationType

from ..decorators import LevelRequiredMixin, OrganizationRequiredMixin, PermissionRequiredMixin
from ..models import Membership, Organization, Role

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(factory, user=None, organization=None, org_permissions=None, org_memberships=None):
    """Build a GET request with the attributes set by OrganizationMiddleware."""
    request = factory.get("/")
    request.user = user or AnonymousUserStub()
    request.organization = organization
    request.org_permissions = org_permissions or []
    request.org_memberships = org_memberships or []
    return request


class AnonymousUserStub:
    """Minimal anonymous-user stand-in (no DB hit required)."""

    is_authenticated = False

    def get_full_path(self):
        return "/"


# ---------------------------------------------------------------------------
# Concrete view classes used in tests
# ---------------------------------------------------------------------------


class _CountingOrgView(OrganizationRequiredMixin, View):
    """Counts how many times the view body was reached."""

    call_count = 0

    def get(self, request, *args, **kwargs):
        type(self).call_count += 1
        return HttpResponse("ok")


class _CountingPermView(PermissionRequiredMixin, View):
    permission_required = "course.view"
    call_count = 0

    def get(self, request, *args, **kwargs):
        type(self).call_count += 1
        return HttpResponse("ok")


class _CountingLevelView(LevelRequiredMixin, View):
    min_level = 50
    call_count = 0

    def get(self, request, *args, **kwargs):
        type(self).call_count += 1
        return HttpResponse("ok")


# ---------------------------------------------------------------------------
# OrganizationRequiredMixin tests
# ---------------------------------------------------------------------------


class OrganizationRequiredMixinDispatchTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        _CountingOrgView.call_count = 0

        self.user = User.objects.create_user(
            username="mixin_test_user",
            email="mixin_test_user@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(
            name="Mixin Test Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )

    def _dispatch(self, request):
        view = _CountingOrgView.as_view()
        return view(request)

    def test_unauthenticated_redirected_view_body_not_reached(self):
        request = _make_request(self.factory)  # anonymous user
        response = self._dispatch(request)
        self.assertEqual(_CountingOrgView.call_count, 0, "View body must not run for anonymous user")
        # Should redirect to login (302)
        self.assertEqual(response.status_code, 302)

    def test_no_organization_redirected_view_body_not_reached(self):
        request = _make_request(self.factory, user=self.user, organization=None)
        response = self._dispatch(request)
        self.assertEqual(_CountingOrgView.call_count, 0, "View body must not run without an active organization")
        self.assertEqual(response.status_code, 302)

    def test_authorized_view_body_reached_exactly_once(self):
        request = _make_request(self.factory, user=self.user, organization=self.org)
        response = self._dispatch(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_CountingOrgView.call_count, 1, "View body must run exactly once for authorized user")


# ---------------------------------------------------------------------------
# PermissionRequiredMixin tests
# ---------------------------------------------------------------------------


class PermissionRequiredMixinDispatchTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        _CountingPermView.call_count = 0

        self.user = User.objects.create_user(
            username="perm_mixin_user",
            email="perm_mixin_user@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(
            name="Perm Mixin Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )

    def _dispatch(self, request):
        view = _CountingPermView.as_view()
        return view(request)

    def test_unauthenticated_redirected_view_body_not_reached(self):
        request = _make_request(self.factory)
        response = self._dispatch(request)
        self.assertEqual(_CountingPermView.call_count, 0)
        self.assertEqual(response.status_code, 302)

    def test_no_organization_redirected_view_body_not_reached(self):
        request = _make_request(self.factory, user=self.user, organization=None)
        response = self._dispatch(request)
        self.assertEqual(_CountingPermView.call_count, 0)
        self.assertEqual(response.status_code, 302)

    def test_missing_permission_forbidden_view_body_not_reached(self):
        request = _make_request(
            self.factory,
            user=self.user,
            organization=self.org,
            org_permissions=[],  # no permissions
        )
        response = self._dispatch(request)
        self.assertEqual(_CountingPermView.call_count, 0, "View body must not run without required permission")
        self.assertEqual(response.status_code, 403)

    def test_authorized_view_body_reached_exactly_once(self):
        request = _make_request(
            self.factory,
            user=self.user,
            organization=self.org,
            org_permissions=["course.view"],
        )
        response = self._dispatch(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_CountingPermView.call_count, 1, "View body must run exactly once for authorized user")

    def test_wildcard_permission_grants_access(self):
        request = _make_request(
            self.factory,
            user=self.user,
            organization=self.org,
            org_permissions=["*"],
        )
        response = self._dispatch(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_CountingPermView.call_count, 1)


# ---------------------------------------------------------------------------
# LevelRequiredMixin tests
# ---------------------------------------------------------------------------


class LevelRequiredMixinDispatchTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        _CountingLevelView.call_count = 0

        self.user = User.objects.create_user(
            username="level_mixin_user",
            email="level_mixin_user@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(
            name="Level Mixin Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )

    def _get_role_with_level(self, level):
        return self.org.roles.get(level=level)

    def _dispatch(self, request):
        view = _CountingLevelView.as_view()
        return view(request)

    def test_unauthenticated_redirected_view_body_not_reached(self):
        request = _make_request(self.factory)
        response = self._dispatch(request)
        self.assertEqual(_CountingLevelView.call_count, 0)
        self.assertEqual(response.status_code, 302)

    def test_no_organization_redirected_view_body_not_reached(self):
        request = _make_request(self.factory, user=self.user, organization=None)
        response = self._dispatch(request)
        self.assertEqual(_CountingLevelView.call_count, 0)
        self.assertEqual(response.status_code, 302)

    def test_insufficient_level_forbidden_view_body_not_reached(self):
        # Use a membership role with level < 50 (min_level for _CountingLevelView)
        member_role = self.org.roles.filter(level__lt=50).first()
        if member_role is None:
            self.skipTest("No role with level < 50 found in this org")

        membership = Membership(user=self.user, organization=self.org, role=member_role)
        request = _make_request(
            self.factory,
            user=self.user,
            organization=self.org,
            org_memberships=[membership],
        )
        response = self._dispatch(request)
        self.assertEqual(_CountingLevelView.call_count, 0, "View body must not run without sufficient level")
        self.assertEqual(response.status_code, 403)

    def test_sufficient_level_view_body_reached_exactly_once(self):
        # Use a membership role with level >= 50
        high_role = self.org.roles.filter(level__gte=50).first()
        if high_role is None:
            self.skipTest("No role with level >= 50 found in this org")

        membership = Membership(user=self.user, organization=self.org, role=high_role)
        request = _make_request(
            self.factory,
            user=self.user,
            organization=self.org,
            org_memberships=[membership],
        )
        response = self._dispatch(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_CountingLevelView.call_count, 1, "View body must run exactly once for authorized user")

    def test_no_memberships_forbidden(self):
        request = _make_request(
            self.factory,
            user=self.user,
            organization=self.org,
            org_memberships=[],  # no memberships → max_level = 0 < 50
        )
        response = self._dispatch(request)
        self.assertEqual(_CountingLevelView.call_count, 0)
        self.assertEqual(response.status_code, 403)
