"""
Shared permission helpers for org-scoped request authorization.
"""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import pgettext

from apps.organizations.permissions import has_permission


def is_teacher(user):
    return getattr(user, "is_teacher_or_above", False)


def is_student(user):
    return getattr(user, "is_student", False)


def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to access this page.")
            return redirect("blog:login")
        if not is_teacher(request.user):
            messages.error(request, "You must be a teacher to access this page.")
            return redirect("blog:index")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def student_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to access this page.")
            return redirect("blog:login")
        if not is_student(request.user):
            messages.error(request, "You must be a student to access this page.")
            return redirect("blog:index")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def is_superadmin_user(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def request_has_permission(request, permission: str) -> bool:
    """
    Permission policy:
    - superadmin/superuser: always allowed
    - user with active-org memberships: must have the requested permission
    - no active-org membership context: allow (legacy profile-scoped fallback)
    """
    if is_superadmin_user(getattr(request, "user", None)):
        return True

    memberships = list(getattr(request, "org_memberships", []) or [])
    if not memberships:
        return True

    org_permissions = list(getattr(request, "org_permissions", []) or [])
    return has_permission(org_permissions, permission)


def ensure_request_permission(request, permission: str, message: str | None = None) -> None:
    if request_has_permission(request, permission):
        return

    raise PermissionDenied(
        message
        or pgettext("core.permission.error", "required_permission_missing").format(permission=permission)
    )
