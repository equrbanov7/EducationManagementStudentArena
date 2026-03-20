"""
Core view mixins for EMS Arena project.

.. removed::
    ``TeacherRequiredMixin`` and ``StudentRequiredMixin`` have been **disabled**
    because they relied on group-based role checks that bypass the organization
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
    "{name} has been removed because it bypassed the organization RBAC model "
    "and could allow cross-tenant data access. "
    "Use apps.organizations.decorators.PermissionRequiredMixin (CBV) or "
    "core.permissions.request_has_permission / ensure_request_permission instead."
)


class TeacherRequiredMixin(AccessMixin):
    """
    .. removed::
        This mixin has been disabled. It used the legacy group-based role system
        (``is_teacher_or_above``) which bypasses the organization RBAC model.
        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        appropriate RBAC permission instead.
    """

    def dispatch(self, request, *args, **kwargs):
        raise ImproperlyConfigured(_REMOVED_MSG.format(name="TeacherRequiredMixin"))


class StudentRequiredMixin(AccessMixin):
    """
    .. removed::
        This mixin has been disabled. It used the legacy group-based role system
        (``is_student``) which bypasses the organization RBAC model.
        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        appropriate RBAC permission instead.
    """

    def dispatch(self, request, *args, **kwargs):
        raise ImproperlyConfigured(_REMOVED_MSG.format(name="StudentRequiredMixin"))


class OwnerRequiredMixin(AccessMixin):
    """
    .. removed::
        This mixin has been disabled. It relied on per-object ownership checks
        that bypass the organization RBAC model and could allow cross-tenant
        data access.

        Preferred replacements
        ~~~~~~~~~~~~~~~~~~~~~~
        * Scope ``get_object_or_404`` to the current user's owned objects and
          combine with ``core.permissions.request_has_permission`` for RBAC
          enforcement.
        * ``apps.organizations.decorators.PermissionRequiredMixin``  – RBAC
          permission guard for class-based views.
    """

    def dispatch(self, request, *args, **kwargs):
        raise ImproperlyConfigured(_REMOVED_MSG.format(name="OwnerRequiredMixin"))
