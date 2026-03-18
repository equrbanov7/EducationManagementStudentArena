"""
Core view mixins for EMS Arena project.

.. removed::
    ``TeacherRequiredMixin`` and ``StudentRequiredMixin`` have been **disabled**
    because they relied on group-based role checks that bypass the organisation
    RBAC model and could allow cross-tenant data access.

    Preferred replacements
    ~~~~~~~~~~~~~~~~~~~~~~
    * ``apps.organizations.decorators.OrganizationRequiredMixin``  – login + org guard.
    * ``apps.organizations.decorators.PermissionRequiredMixin``  – RBAC permission guard.
    * ``apps.organizations.decorators.LevelRequiredMixin``  – role-level guard.
    * ``core.permissions.request_has_permission`` / ``ensure_request_permission``
      for inline checks inside views.
"""

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ImproperlyConfigured

_REMOVED_MSG = (
    "{name} has been removed because it bypassed the organisation RBAC model "
    "and could allow cross-tenant data access. "
    "Use apps.organizations.decorators.PermissionRequiredMixin (CBV) or "
    "core.permissions.request_has_permission / ensure_request_permission instead."
)


class TeacherRequiredMixin(AccessMixin):
    """
    .. removed::
        This mixin has been disabled. It used the legacy group-based role system
        (``is_teacher_or_above``) which bypasses the organisation RBAC model.
        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        appropriate RBAC permission instead.
    """

    def dispatch(self, request, *args, **kwargs):
        raise ImproperlyConfigured(
            _REMOVED_MSG.format(name="TeacherRequiredMixin")
        )


class StudentRequiredMixin(AccessMixin):
    """
    .. removed::
        This mixin has been disabled. It used the legacy group-based role system
        (``is_student``) which bypasses the organisation RBAC model.
        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        appropriate RBAC permission instead.
    """

    def dispatch(self, request, *args, **kwargs):
        raise ImproperlyConfigured(
            _REMOVED_MSG.format(name="StudentRequiredMixin")
        )


class OwnerRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be the owner of the object.

    .. deprecated::
        Use object-level permission checks (e.g. ``get_object_or_404`` scoped to
        the current user) combined with ``core.permissions.request_has_permission``
        for RBAC enforcement instead of this mixin.
    """

    def dispatch(self, request, *args, **kwargs):
        import warnings
        warnings.warn(
            "OwnerRequiredMixin is deprecated. "
            "Use apps.organizations.decorators.OrganizationRequiredMixin / "
            "PermissionRequiredMixin, or core.permissions.request_has_permission instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from django.contrib import messages
        from django.shortcuts import redirect
        obj = self.get_object()
        if obj.user != request.user and not request.user.is_staff:
            messages.error(request, "You don't have permission to access this page.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)
