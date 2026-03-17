"""
Core view mixins for EMS Arena project.

.. deprecated::
    All mixins in this module are **deprecated** because they rely on
    group-based role checks (``is_teacher_or_above``, ``is_student``) that
    bypass the organisation RBAC model.

    Preferred replacements
    ~~~~~~~~~~~~~~~~~~~~~~
    * ``apps.organizations.decorators.OrganizationRequiredMixin``  – login + org guard.
    * ``apps.organizations.decorators.PermissionRequiredMixin``  – RBAC permission guard.
    * ``apps.organizations.decorators.LevelRequiredMixin``  – role-level guard.
    * ``core.permissions.request_has_permission`` / ``ensure_request_permission``
      for inline checks inside views.
"""

import warnings

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect

_DEPRECATION_HINT = (
    "Use apps.organizations.decorators.OrganizationRequiredMixin / "
    "PermissionRequiredMixin, or core.permissions.request_has_permission instead."
)


class TeacherRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be a teacher or higher role.

    .. deprecated::
        Uses the legacy group-based role system (``is_teacher_or_above``).
        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        appropriate RBAC permission instead.
    """

    def dispatch(self, request, *args, **kwargs):
        warnings.warn(
            "TeacherRequiredMixin is deprecated. " + _DEPRECATION_HINT,
            DeprecationWarning,
            stacklevel=2,
        )
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request.user, "is_teacher_or_above", False):
            messages.error(request, "You must be a teacher to access this page.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be a student.

    .. deprecated::
        Uses the legacy group-based role system (``is_student``).
        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        appropriate RBAC permission instead.
    """

    def dispatch(self, request, *args, **kwargs):
        warnings.warn(
            "StudentRequiredMixin is deprecated. " + _DEPRECATION_HINT,
            DeprecationWarning,
            stacklevel=2,
        )
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request.user, "is_student", False):
            messages.error(request, "You must be a student to access this page.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)


class OwnerRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be the owner of the object.

    .. deprecated::
        Use object-level permission checks (e.g. ``get_object_or_404`` scoped to
        the current user) combined with ``core.permissions.request_has_permission``
        for RBAC enforcement instead of this mixin.
    """

    def dispatch(self, request, *args, **kwargs):
        warnings.warn(
            "OwnerRequiredMixin is deprecated. " + _DEPRECATION_HINT,
            DeprecationWarning,
            stacklevel=2,
        )
        obj = self.get_object()
        if obj.user != request.user and not request.user.is_staff:
            messages.error(request, "You don't have permission to access this page.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)
