"""
Tests for the unified RBAC authorization layer.

Covers:
* ``core.permissions.request_has_permission`` – primary inline check.
* ``core.permissions.ensure_request_permission`` – raises PermissionDenied.
* ``core.permissions.teacher_required`` / ``student_required`` – removed decorators.
* ``core.mixins.TeacherRequiredMixin`` / ``StudentRequiredMixin`` / ``OwnerRequiredMixin`` – removed mixins.
* ``apps.courses.views._helpers.IsTeacherMixin`` – removed local mixin.
* ``apps.organizations.decorators`` FBV decorators – removed (hard-fail).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.test import RequestFactory, TestCase

from core.permissions import (
    ensure_request_permission,
    request_has_permission,
    student_required,
    teacher_required,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_request(user=None, organization=None, org_permissions=None, org_memberships=None):
    """Build a minimal request for unit-testing permission helpers."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user or SimpleNamespace(is_authenticated=False, is_superuser=False)
    request.organization = organization
    request.org_permissions = org_permissions or []
    request.org_memberships = org_memberships or []
    return request


def _membership_stub(level: int):
    """Create a membership stub with a given role level."""
    role = SimpleNamespace(level=level, name="teacher")
    return SimpleNamespace(role=role)


# ---------------------------------------------------------------------------
# request_has_permission tests
# ---------------------------------------------------------------------------


class RequestHasPermissionTest(TestCase):
    """Tests for core.permissions.request_has_permission."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="perm_test_user",
            email="perm@example.com",
            password="testpass123",
        )

    def test_no_org_context_returns_false(self):
        request = _make_request(
            user=self.user,
            organization=None,
            org_memberships=[_membership_stub(50)],
        )
        self.assertFalse(request_has_permission(request, "course.create"))

    def test_no_memberships_returns_false(self):
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        request = _make_request(
            user=self.user,
            organization=org,
            org_memberships=[],
        )
        self.assertFalse(request_has_permission(request, "course.create"))

    def test_matching_permission_returns_true(self):
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        request = _make_request(
            user=self.user,
            organization=org,
            org_permissions=["course.create"],
            org_memberships=[_membership_stub(50)],
        )
        self.assertTrue(request_has_permission(request, "course.create"))

    def test_missing_permission_returns_false(self):
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        request = _make_request(
            user=self.user,
            organization=org,
            org_permissions=["course.view"],
            org_memberships=[_membership_stub(50)],
        )
        self.assertFalse(request_has_permission(request, "course.create"))

    def test_superuser_returns_true_without_explicit_permission(self):
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        superuser = User.objects.create_superuser(
            username="perm_superuser",
            email="super@example.com",
            password="testpass123",
        )
        request = _make_request(
            user=superuser,
            organization=org,
            org_permissions=[],
            org_memberships=[],
        )
        self.assertTrue(request_has_permission(request, "course.delete"))

    def test_wildcard_permission_returns_true(self):
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        request = _make_request(
            user=self.user,
            organization=org,
            org_permissions=["*"],
            org_memberships=[_membership_stub(50)],
        )
        self.assertTrue(request_has_permission(request, "exam.delete"))

    def test_superadmin_cross_org_audit_log_failure_does_not_block_request(self):
        """Audit log exception must not block a superadmin cross-org request; logger.exception() is called."""
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        superuser = User.objects.create_superuser(
            username="perm_superuser_audit",
            email="superaudit@example.com",
            password="testpass123",
        )
        request = _make_request(
            user=superuser,
            organization=org,
            org_permissions=[],
            org_memberships=[],
        )

        with patch(
            "apps.audit.utils.log_superadmin_cross_org_action",
            side_effect=Exception("audit failure"),
        ), patch("core.permissions.logger") as mock_logger:
            result = request_has_permission(request, "course.delete")

        self.assertTrue(result)
        mock_logger.exception.assert_called_once_with("Failed to log superadmin cross-org action")


# ---------------------------------------------------------------------------
# ensure_request_permission tests
# ---------------------------------------------------------------------------


class EnsureRequestPermissionTest(TestCase):
    """Tests for core.permissions.ensure_request_permission."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ensure_perm_user",
            email="ensureperm@example.com",
            password="testpass123",
        )

    def test_raises_permission_denied_when_permission_missing(self):
        request = _make_request(user=self.user, organization=None)
        with self.assertRaises(PermissionDenied):
            ensure_request_permission(request, "course.create")

    def test_passes_silently_when_permission_present(self):
        from apps.organizations.models import Organization

        org = MagicMock(spec=Organization)
        request = _make_request(
            user=self.user,
            organization=org,
            org_permissions=["course.create"],
            org_memberships=[_membership_stub(50)],
        )
        # Should not raise
        ensure_request_permission(request, "course.create")


# ---------------------------------------------------------------------------
# Removed legacy core.permissions decorator tests
# ---------------------------------------------------------------------------


class RemovedDecoratorTest(TestCase):
    """Removed ``teacher_required`` and ``student_required`` raise ImproperlyConfigured."""

    def test_teacher_required_raises_improperly_configured(self):
        @teacher_required
        def dummy_view(request):
            return "ok"

        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(ImproperlyConfigured) as ctx:
            dummy_view(request)

        self.assertIn("teacher_required", str(ctx.exception))
        self.assertIn("RBAC", str(ctx.exception))

    def test_student_required_raises_improperly_configured(self):
        @student_required
        def dummy_view(request):
            return "ok"

        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(ImproperlyConfigured) as ctx:
            dummy_view(request)

        self.assertIn("student_required", str(ctx.exception))
        self.assertIn("RBAC", str(ctx.exception))


# ---------------------------------------------------------------------------
# Removed core.mixins mixin tests
# ---------------------------------------------------------------------------


class RemovedMixinsTest(TestCase):
    """Removed ``core.mixins`` classes raise ImproperlyConfigured on dispatch."""

    def test_teacher_required_mixin_raises_improperly_configured(self):
        from django.http import HttpResponse
        from django.views import View

        from core.mixins import TeacherRequiredMixin

        class _View(TeacherRequiredMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(ImproperlyConfigured) as ctx:
            _View.as_view()(request)

        self.assertIn("TeacherRequiredMixin", str(ctx.exception))
        self.assertIn("RBAC", str(ctx.exception))

    def test_student_required_mixin_raises_improperly_configured(self):
        from django.http import HttpResponse
        from django.views import View

        from core.mixins import StudentRequiredMixin

        class _View(StudentRequiredMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(ImproperlyConfigured) as ctx:
            _View.as_view()(request)

        self.assertIn("StudentRequiredMixin", str(ctx.exception))
        self.assertIn("RBAC", str(ctx.exception))

    def test_owner_required_mixin_raises_improperly_configured(self):
        from django.http import HttpResponse
        from django.views import View

        from core.mixins import OwnerRequiredMixin

        class _View(OwnerRequiredMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(ImproperlyConfigured) as ctx:
            _View.as_view()(request)

        self.assertIn("OwnerRequiredMixin", str(ctx.exception))
        self.assertIn("RBAC", str(ctx.exception))


# ---------------------------------------------------------------------------
# Removed org decorators tests
# ---------------------------------------------------------------------------


class RemovedOrgDecoratorsTest(TestCase):
    """Removed FBV decorators in apps.organizations.decorators raise ImproperlyConfigured."""

    def test_org_required_raises_improperly_configured(self):
        from apps.organizations.decorators import org_required

        @org_required
        def dummy_view(request):
            return "ok"

        factory = RequestFactory()
        request = factory.get("/")

        with self.assertRaises(ImproperlyConfigured) as ctx:
            dummy_view(request)

        self.assertIn("org_required", str(ctx.exception))

    def test_org_permission_required_raises_improperly_configured(self):
        from apps.organizations.decorators import org_permission_required

        @org_permission_required("course.create")
        def dummy_view(request):
            return "ok"

        factory = RequestFactory()
        request = factory.get("/")

        with self.assertRaises(ImproperlyConfigured) as ctx:
            dummy_view(request)

        self.assertIn("org_permission_required", str(ctx.exception))

    def test_org_level_required_raises_improperly_configured(self):
        from apps.organizations.decorators import org_level_required

        @org_level_required(10)
        def dummy_view(request):
            return "ok"

        factory = RequestFactory()
        request = factory.get("/")

        with self.assertRaises(ImproperlyConfigured) as ctx:
            dummy_view(request)

        self.assertIn("org_level_required", str(ctx.exception))

    def test_org_role_required_raises_improperly_configured(self):
        from apps.organizations.decorators import org_role_required

        @org_role_required("teacher")
        def dummy_view(request):
            return "ok"

        factory = RequestFactory()
        request = factory.get("/")

        with self.assertRaises(ImproperlyConfigured) as ctx:
            dummy_view(request)

        self.assertIn("org_role_required", str(ctx.exception))


# ---------------------------------------------------------------------------
# IsTeacherMixin removal
# ---------------------------------------------------------------------------


class IsTeacherMixinRemovedTest(TestCase):
    """IsTeacherMixin in courses.views._helpers raises ImproperlyConfigured."""

    def test_is_teacher_mixin_raises_improperly_configured(self):
        from django.http import HttpResponse
        from django.views import View

        from apps.courses.views._helpers import IsTeacherMixin

        class _CourseView(IsTeacherMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        factory = RequestFactory()
        request = factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with self.assertRaises(ImproperlyConfigured) as ctx:
            _CourseView.as_view()(request)

        self.assertIn("IsTeacherMixin", str(ctx.exception))
        self.assertIn("RBAC", str(ctx.exception))
