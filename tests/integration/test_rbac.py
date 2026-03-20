"""
Integration tests – RBAC & Permissions.

Verifies that:
* ``request_has_permission`` returns False when the request has no active
  organization context.
* ``PermissionRequiredMixin`` sends a 403 when the user lacks the required
  permission.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.views import View

from apps.organizations.decorators import PermissionRequiredMixin
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType
from core.permissions import request_has_permission

User = get_user_model()


# ---------------------------------------------------------------------------
# Minimal view for mixin tests
# ---------------------------------------------------------------------------


class _ProtectedView(PermissionRequiredMixin, View):
    permission_required = "course.view"

    def get(self, request, *args, **kwargs):
        return HttpResponse("ok", status=200)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class RequestHasPermissionTest(TestCase):
    """Unit tests for ``core.permissions.request_has_permission``."""

    def _make_request(self, *, organization=None, org_permissions=None, org_memberships=None, user=None):
        factory = RequestFactory()
        request = factory.get("/")
        if user is None:
            request.user = SimpleNamespace(
                is_authenticated=True,
                is_superuser=False,
                pk=1,
            )
        else:
            request.user = user
        request.organization = organization
        request.org_permissions = org_permissions or []
        request.org_memberships = org_memberships or []
        return request

    def test_request_has_permission_returns_false_without_org(self):
        """
        ``request_has_permission`` must return False when there is no active
        organization on the request (i.e., missing org context).
        """
        request = self._make_request(organization=None)
        result = request_has_permission(request, "course.view")
        self.assertFalse(
            result,
            "request_has_permission must return False when organization context is absent",
        )

    def test_request_has_permission_returns_false_without_memberships(self):
        """
        Even with an active organization, an empty memberships list must cause
        the permission check to return False.
        """
        factory = RequestFactory()
        request = factory.get("/")
        # Minimal authenticated user stub
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            pk=1,
        )
        # Provide an org object so context check passes
        org = SimpleNamespace(slug="test-org")
        request.organization = org
        request.org_permissions = ["course.view"]
        request.org_memberships = []  # no memberships
        result = request_has_permission(request, "course.view")
        self.assertFalse(
            result,
            "request_has_permission must return False when org_memberships is empty",
        )

    def test_request_has_permission_returns_true_with_matching_permission(self):
        """
        A request with an active organization, at least one membership, and the
        relevant permission entry must return True.
        """
        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            pk=1,
        )
        org = SimpleNamespace(slug="test-org")
        request.organization = org
        request.org_permissions = ["course.view"]
        request.org_memberships = [SimpleNamespace(role=SimpleNamespace(level=60, name="teacher"))]
        result = request_has_permission(request, "course.view")
        self.assertTrue(result)


class PermissionRequiredMixinTest(TestCase):
    """Integration tests for ``PermissionRequiredMixin``."""

    def setUp(self):
        self.factory = RequestFactory()

        post_save.disconnect(create_default_roles, sender=Organization)
        self.user = User.objects.create_user(
            username="rbac_mixin_user",
            email="rbac_mixin@example.com",
            password="testpass123",
        )
        self.org = Organization.objects.create(
            name="RBAC Mixin Org",
            slug="rbac-mixin-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
            status="active",
            is_active=True,
        )
        self.role_no_perm = Role.objects.create(
            organization=self.org,
            name="student",
            display_name="Student",
            level=20,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=[],  # deliberately no permissions
            is_active=True,
        )
        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=self.role_no_perm,
            is_primary=True,
            is_active=True,
        )
        post_save.connect(create_default_roles, sender=Organization)

    def _make_request(self, *, user=None, organization=None, org_permissions=None, org_memberships=None):
        request = self.factory.get("/")
        request.user = user or self.user
        request.organization = organization
        request.org_permissions = org_permissions or []
        request.org_memberships = org_memberships or []
        return request

    def test_permission_required_mixin_denies_without_permission(self):
        """
        A request with an active organization but without the required
        ``course.view`` permission must receive HTTP 403.
        """
        request = self._make_request(
            organization=self.org,
            org_permissions=[],  # user has no permissions
            org_memberships=[self.membership],
        )
        response = _ProtectedView.as_view()(request)
        self.assertEqual(
            response.status_code,
            403,
            "PermissionRequiredMixin must return 403 when the user lacks the required permission",
        )

    def test_permission_required_mixin_denies_without_org(self):
        """
        A request without an active organization must be redirected (not 200).
        """
        request = self._make_request(organization=None)
        response = _ProtectedView.as_view()(request)
        # Redirect to organization select page
        self.assertIn(response.status_code, (302, 403))

    def test_permission_required_mixin_allows_with_correct_permission(self):
        """
        A request with the correct permission must reach the view and return 200.
        """
        request = self._make_request(
            organization=self.org,
            org_permissions=["course.view"],
            org_memberships=[self.membership],
        )
        response = _ProtectedView.as_view()(request)
        self.assertEqual(response.status_code, 200)
