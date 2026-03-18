"""
Primary authorization entry point for EMS Arena.

This module is the single standard authorization layer for the project.

Canonical authorization API
----------------------------
* ``request_has_permission(request, permission)``  – Boolean check (FBV / inline).
* ``ensure_request_permission(request, permission)``  – Raises PermissionDenied.
* ``apps.organizations.decorators.OrganizationRequiredMixin``  – CBV guard (login + org).
* ``apps.organizations.decorators.PermissionRequiredMixin``  – CBV guard + RBAC permission.
* ``apps.organizations.decorators.LevelRequiredMixin``  – CBV guard + role level.

Removed legacy helpers
----------------------
The following group-based helpers have been **removed** because they bypassed
the organization RBAC model and allowed cross-tenant access:

* ``teacher_required``  – use ``request_has_permission`` or RBAC-aware CBV mixins.
* ``student_required``  – same as above.

``core.mixins.TeacherRequiredMixin`` / ``StudentRequiredMixin`` are similarly
removed; see ``core/mixins.py``.
"""

from __future__ import annotations

from functools import wraps

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.utils.translation import pgettext

from apps.organizations.permissions import has_permission
from core.tenancy import request_has_active_organization_context

_REMOVED_MSG = (
    "{name} has been removed because it bypassed the organization RBAC model "
    "and could allow cross-tenant data access. "
    "Use apps.organizations.decorators.PermissionRequiredMixin (CBV) or "
    "core.permissions.request_has_permission / ensure_request_permission (FBV) instead."
)


def is_teacher(user):
    return getattr(user, "is_teacher_or_above", False)


def is_student(user):
    return getattr(user, "is_student", False)


def teacher_required(view_func):
    """
    .. removed::
        This decorator has been disabled because it bypasses the organization
        RBAC model. Use ``request_has_permission(request, '<permission>')`` or
        ``apps.organizations.decorators.PermissionRequiredMixin`` instead.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        raise ImproperlyConfigured(
            _REMOVED_MSG.format(name="teacher_required")
        )

    return _wrapped_view


def student_required(view_func):
    """
    .. removed::
        This decorator has been disabled because it bypasses the organization
        RBAC model. Use ``request_has_permission(request, '<permission>')`` or
        ``apps.organizations.decorators.PermissionRequiredMixin`` instead.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        raise ImproperlyConfigured(
            _REMOVED_MSG.format(name="student_required")
        )

    return _wrapped_view


def is_superadmin_user(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def request_has_permission(request, permission: str) -> bool:
    """
    Permission policy:
    - active organization context is required
    - superadmin/superuser: allowed within an active organization
    - user with active-org memberships: must have the requested permission
    - missing org context or memberships: deny
    """
    if not request_has_active_organization_context(request):
        return False

    if is_superadmin_user(getattr(request, "user", None)):
        return True

    memberships = list(getattr(request, "org_memberships", []) or [])
    if not memberships:
        return False

    org_permissions = list(getattr(request, "org_permissions", []) or [])
    return has_permission(org_permissions, permission)


def ensure_request_permission(request, permission: str, message: str | None = None) -> None:
    if request_has_permission(request, permission):
        return

    if not request_has_active_organization_context(request):
        raise PermissionDenied(message or pgettext("core.permission.error", "An active organization is required."))

    raise PermissionDenied(
        message
        or pgettext("core.permission.error", "required_permission_missing").format(permission=permission)
    )
