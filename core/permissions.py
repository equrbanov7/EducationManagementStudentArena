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

Deprecated helpers
------------------
The following group-based helpers bypass the RBAC model and are **deprecated**.
They still function but emit ``DeprecationWarning`` at call-time:

* ``teacher_required``  – use ``request_has_permission`` or RBAC-aware CBV mixins.
* ``student_required``  – same as above.

``core.mixins.TeacherRequiredMixin`` / ``StudentRequiredMixin`` are similarly
deprecated; see ``core/mixins.py``.
"""

from __future__ import annotations

import warnings
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import pgettext

from apps.organizations.permissions import has_permission
from core.tenancy import request_has_active_organization_context


def is_teacher(user):
    return getattr(user, "is_teacher_or_above", False)


def is_student(user):
    return getattr(user, "is_student", False)


def teacher_required(view_func):
    """
    .. deprecated::
        Use ``request_has_permission(request, '<permission>')`` or
        ``apps.organizations.decorators.PermissionRequiredMixin`` instead.
        This decorator performs a simple group-based check and bypasses the
        organisation RBAC model.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        warnings.warn(
            "teacher_required is deprecated and will be removed in a future release. "
            "Use request_has_permission() or PermissionRequiredMixin from "
            "apps.organizations.decorators instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to access this page.")
            return redirect("accounts:login")
        if not is_teacher(request.user):
            messages.error(request, "You must be a teacher to access this page.")
            return redirect("home")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def student_required(view_func):
    """
    .. deprecated::
        Use ``request_has_permission(request, '<permission>')`` or
        ``apps.organizations.decorators.PermissionRequiredMixin`` instead.
        This decorator performs a simple group-based check and bypasses the
        organisation RBAC model.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        warnings.warn(
            "student_required is deprecated and will be removed in a future release. "
            "Use request_has_permission() or PermissionRequiredMixin from "
            "apps.organizations.decorators instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to access this page.")
            return redirect("accounts:login")
        if not is_student(request.user):
            messages.error(request, "You must be a student to access this page.")
            return redirect("home")
        return view_func(request, *args, **kwargs)

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
