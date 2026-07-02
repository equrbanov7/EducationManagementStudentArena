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

import logging
from functools import wraps

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.utils.translation import pgettext

from core.tenancy import request_has_active_organization_context

logger = logging.getLogger(__name__)

# ── M3 (2026-07-02): permission-string uyğunlaşdırma məntiqi organizations-dan
# core-a köçürülüb (core→organizations kənarını kəsir); organizations.permissions
# geriyə-uyğun re-export saxlayır. Pure string əməliyyatlarıdır.

# This map is kept ONLY as a transitional safety net so that any role data
# that somehow still carries a legacy spelling keeps working. Once it is
# confirmed in production that no legacy spellings remain (e.g. a DB audit),
# this map and the alias-handling branches below can be deleted outright.
PERMISSION_PREFIX_ALIASES = {
    "grade": "grading",
    "grading": "grade",
    "course": "courses",
    "courses": "course",
    "exam": "exams",
    "exams": "exam",
    "member": "members",
    "members": "member",
    "role": "roles",
    "roles": "role",
}


def _permission_variants(permission: str) -> set[str]:
    variants = {permission}
    if "." not in permission:
        return variants

    prefix, suffix = permission.split(".", 1)
    alias_prefix = PERMISSION_PREFIX_ALIASES.get(prefix)
    if alias_prefix:
        variants.add(f"{alias_prefix}.{suffix}")
    return variants


def _wildcard_variants(prefix: str) -> set[str]:
    variants = {f"{prefix}.*"}
    alias_prefix = PERMISSION_PREFIX_ALIASES.get(prefix)
    if alias_prefix:
        variants.add(f"{alias_prefix}.*")
    return variants


def has_permission(user_permissions: list[str], required_permission: str) -> bool:
    """
    Check if a user has a specific permission.
    Supports wildcard permissions (e.g., '*' for all, 'course.*' for all course permissions).
    Also tolerates the legacy `grading.*` prefix when checking `grade.*` permissions.

    Args:
        user_permissions: List of permission strings the user has
        required_permission: The permission string to check for

    Returns:
        True if user has the permission, False otherwise
    """
    if not user_permissions:
        return False

    if "*" in user_permissions:
        return True

    if _permission_variants(required_permission).intersection(user_permissions):
        return True

    if "." in required_permission:
        prefix = required_permission.split(".", 1)[0]
        if _wildcard_variants(prefix).intersection(user_permissions):
            return True

    return False


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
        raise ImproperlyConfigured(_REMOVED_MSG.format(name="teacher_required"))

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
        raise ImproperlyConfigured(_REMOVED_MSG.format(name="student_required"))

    return _wrapped_view


def is_superadmin_user(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def request_has_permission(request, permission: str) -> bool:
    """
    Permission policy:
    - active organization context is required
    - superadmin/superuser: allowed within an active organization; their
      cross-org actions are recorded in the audit log automatically.
    - user with active-org memberships: must have the requested permission
    - missing org context or memberships: deny
    """
    if not request_has_active_organization_context(request):
        return False

    user = getattr(request, "user", None)
    if is_superadmin_user(user):
        # When the superadmin has no membership in the current org they are
        # operating cross-org.  Record an audit trail entry so that every such
        # permission check is traceable.
        memberships = list(getattr(request, "org_memberships", []) or [])
        if not memberships:
            try:
                from core.audit import log_superadmin_cross_org_action

                log_superadmin_cross_org_action(
                    request,
                    action="view",
                    reason=f"Superadmin permission check bypassed membership for '{permission}'",
                )
            except Exception:
                logger.exception("Failed to log superadmin cross-org action")
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
        message or pgettext("core.permission.error", "required_permission_missing").format(permission=permission)
    )
