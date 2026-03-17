"""
courses/views/_helpers.py
──────────────────────────
Course-specific helper functions and mixins.

Authorization convention for this app
--------------------------------------
* **Inline RBAC checks** – use ``_require_org_permission(request, '<permission>')``
  (wraps ``core.permissions.ensure_request_permission``).
* **Object ownership guards** – use ``IsCourseOwnerMixin`` which scopes the
  queryset to the current user's owned courses.
* ``IsTeacherMixin`` is **deprecated** (simple group-based check). Prefer
  ``LoginRequiredMixin`` combined with an inline ``_require_org_permission`` call.
"""

import warnings

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext

from apps.courses.models import Course
from core.helpers import _tenant_scoped_courses
from core.permissions import request_has_permission


# ════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ════════════════════════════════════════════════════════════════════════════


def _owner_courses_queryset(request):
    """Get courses owned by the current user, scoped to tenant."""
    return _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))


def _get_owner_course_or_404(request, course_id):
    """Get a course owned by the current user or raise 404."""
    return get_object_or_404(_owner_courses_queryset(request), id=course_id)


def _student_users_queryset(queryset):
    """Filter a user queryset to only include students."""
    return queryset.filter(
        Q(profile__role__in=["student", "lead_student"]) | Q(groups__name__in=["student", "lead_student"])
    ).distinct()


def _require_org_permission(request, permission):
    """Require that the request user has a specific organization permission."""
    if request_has_permission(request, permission):
        return
    raise PermissionDenied(
        pgettext("courses.view.permission", "required_permission_missing").format(permission=permission)
    )


# ════════════════════════════════════════════════════════════════════════════
# Mixins
# ════════════════════════════════════════════════════════════════════════════


class IsTeacherMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Yalnız müəllim (is_teacher_or_above) bu view-a girə bilər.

    .. deprecated::
        Uses the legacy group-based role check (``is_teacher_or_above``).  Prefer
        ``LoginRequiredMixin`` combined with an inline
        ``_require_org_permission(request, '<permission>')`` call inside the view
        method that actually needs the RBAC guard.
    """

    def dispatch(self, request, *args, **kwargs):
        warnings.warn(
            "IsTeacherMixin is deprecated. Use LoginRequiredMixin combined with "
            "_require_org_permission() or core.permissions.ensure_request_permission() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return getattr(self.request.user, "is_teacher_or_above", False)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(pgettext("courses.view.permission", "teachers_only_action"))


class IsCourseOwnerMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Yalnız kursun sahibi (owner) redaktə edə bilər."""

    def test_func(self):
        course_id = self.kwargs.get("course_id")
        return _owner_courses_queryset(self.request).filter(id=course_id).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(pgettext("courses.view.permission", "no_permission_edit_course"))
