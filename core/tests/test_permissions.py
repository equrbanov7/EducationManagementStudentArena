"""
Tests for the unified RBAC authorization layer.

Covers:
* ``core.permissions.request_has_permission`` – primary inline check.
* ``core.permissions.ensure_request_permission`` – raises PermissionDenied.
* ``core.permissions.teacher_required`` / ``student_required`` – deprecated decorators.
* ``core.mixins.TeacherRequiredMixin`` / ``StudentRequiredMixin`` – deprecated mixins.
* ``apps.courses.views._helpers.IsTeacherMixin`` – deprecated local mixin.
* ``apps.organizations.decorators`` FBV decorators – deprecated.
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
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
# Deprecated core.permissions decorator tests
# ---------------------------------------------------------------------------


class DeprecatedDecoratorTest(TestCase):
    """Deprecated ``teacher_required`` and ``student_required`` emit DeprecationWarning."""

    def test_teacher_required_emits_deprecation_warning(self):
        @teacher_required
        def dummy_view(request):
            return "ok"

        # Use SimpleNamespace so we can freely set the group-based property
        # that the deprecated decorator checks.
        user = SimpleNamespace(
            is_authenticated=True,
            is_teacher_or_above=True,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.session = {}
        request._messages = MagicMock()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dummy_view(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("teacher_required" in str(w.message) for w in deprecation_warnings),
            "teacher_required should emit a DeprecationWarning",
        )

    def test_student_required_emits_deprecation_warning(self):
        @student_required
        def dummy_view(request):
            return "ok"

        user = SimpleNamespace(
            is_authenticated=True,
            is_student=True,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.session = {}
        request._messages = MagicMock()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dummy_view(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("student_required" in str(w.message) for w in deprecation_warnings),
            "student_required should emit a DeprecationWarning",
        )


# ---------------------------------------------------------------------------
# Deprecated core.mixins mixin tests
# ---------------------------------------------------------------------------


class DeprecatedMixinsTest(TestCase):
    """Deprecated ``core.mixins`` classes emit DeprecationWarning on dispatch."""

    def test_teacher_required_mixin_emits_deprecation_warning(self):
        from django.http import HttpResponse
        from django.views import View

        from core.mixins import TeacherRequiredMixin

        class _View(TeacherRequiredMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        # Use SimpleNamespace so we can freely set the group-based property.
        user = SimpleNamespace(
            is_authenticated=True,
            is_teacher_or_above=True,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request._messages = MagicMock()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _View.as_view()(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("TeacherRequiredMixin" in str(w.message) for w in deprecation_warnings),
        )

    def test_student_required_mixin_emits_deprecation_warning(self):
        from django.http import HttpResponse
        from django.views import View

        from core.mixins import StudentRequiredMixin

        class _View(StudentRequiredMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        user = SimpleNamespace(
            is_authenticated=True,
            is_student=True,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request._messages = MagicMock()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _View.as_view()(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("StudentRequiredMixin" in str(w.message) for w in deprecation_warnings),
        )


# ---------------------------------------------------------------------------
# Deprecated org decorators tests
# ---------------------------------------------------------------------------


class DeprecatedOrgDecoratorsTest(TestCase):
    """Deprecated FBV decorators in apps.organizations.decorators emit DeprecationWarning."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="org_dec_user",
            email="orgdec@example.com",
            password="testpass123",
        )

    def _make_org_request(self, org_permissions=None, level=50):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        request.organization = MagicMock()
        request.org_permissions = org_permissions or []
        request.org_memberships = [_membership_stub(level)]
        return request

    def test_org_permission_required_emits_deprecation_warning(self):
        from apps.organizations.decorators import org_permission_required

        @org_permission_required("course.create")
        def dummy_view(request):
            return "ok"

        request = self._make_org_request(org_permissions=["course.create"])

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dummy_view(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("org_permission_required" in str(w.message) for w in deprecation_warnings),
        )

    def test_org_level_required_emits_deprecation_warning(self):
        from apps.organizations.decorators import org_level_required

        @org_level_required(10)
        def dummy_view(request):
            return "ok"

        request = self._make_org_request(level=50)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dummy_view(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("org_level_required" in str(w.message) for w in deprecation_warnings),
        )

    def test_org_role_required_emits_deprecation_warning(self):
        from apps.organizations.decorators import org_role_required

        @org_role_required("teacher")
        def dummy_view(request):
            return "ok"

        request = self._make_org_request()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dummy_view(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("org_role_required" in str(w.message) for w in deprecation_warnings),
        )


# ---------------------------------------------------------------------------
# IsTeacherMixin deprecation
# ---------------------------------------------------------------------------


class IsTeacherMixinDeprecationTest(TestCase):
    """IsTeacherMixin in courses.views._helpers emits DeprecationWarning."""

    def test_is_teacher_mixin_emits_deprecation_warning(self):
        from django.http import HttpResponse
        from django.views import View

        from apps.courses.views._helpers import IsTeacherMixin

        class _CourseView(IsTeacherMixin, View):
            def get(self, request, *args, **kwargs):
                return HttpResponse("ok")

        # Use SimpleNamespace so we can freely set the group-based property.
        user = SimpleNamespace(
            is_authenticated=True,
            is_teacher_or_above=True,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _CourseView.as_view()(request)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("IsTeacherMixin" in str(w.message) for w in deprecation_warnings),
        )
