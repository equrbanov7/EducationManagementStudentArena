"""
Canonical class-based-view authorization layer for EMS Arena.

This module provides the **authoritative** set of class-based-view mixins and
function-based-view decorators that enforce the organisation RBAC model.

Canonical CBV API (preferred)
------------------------------
* ``OrganizationRequiredMixin``  – Ensures the user is logged in and has an
  active organisation context.  Use as the base mixin for all org-scoped views.
* ``PermissionRequiredMixin``  – Extends ``OrganizationRequiredMixin`` and
  checks a specific RBAC permission string (e.g. ``'course.create'``).
* ``LevelRequiredMixin``  – Extends ``OrganizationRequiredMixin`` and checks
  that the user's highest role level meets a minimum threshold.

Canonical FBV/inline API (preferred)
--------------------------------------
* ``core.permissions.request_has_permission(request, permission)``  – Boolean
  check for inline use inside view functions.
* ``core.permissions.ensure_request_permission(request, permission)``  – Raises
  ``PermissionDenied`` when the permission is absent.

Removed function decorators
-----------------------------
The following function-based decorators have been **removed** and will raise
``ImproperlyConfigured`` if called.  Migrate all usages to the canonical
CBV mixins or the ``core.permissions`` inline helpers above.

* ``org_required``  – use ``OrganizationRequiredMixin`` on CBVs or add a
  ``@login_required`` + org guard in FBVs.
* ``org_permission_required``  – use ``PermissionRequiredMixin`` or
  ``ensure_request_permission``.
* ``org_level_required``  – use ``LevelRequiredMixin``.
* ``org_role_required``  – use ``PermissionRequiredMixin`` with an RBAC
  permission that maps to the required role capability.
"""

from functools import wraps

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.translation import pgettext

from .permissions import has_permission

_FBV_REMOVED_HINT = (
    "Use OrganizationRequiredMixin / PermissionRequiredMixin / LevelRequiredMixin "
    "(class-based views) or core.permissions.ensure_request_permission (inline) instead."
)


def org_required(view_func):
    """
    .. removed::
        This decorator has been removed. It relied on a simple org-presence
        check that bypasses the organization RBAC model.

        Use ``apps.organizations.decorators.OrganizationRequiredMixin`` for
        class-based views or a manual ``@login_required`` + org guard for
        function-based views.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        raise ImproperlyConfigured(
            "org_required has been removed. " + _FBV_REMOVED_HINT
        )

    return wrapper


def org_permission_required(permission):
    """
    .. removed::
        This decorator has been removed. It relied on a permission check that
        bypasses the organization RBAC model.

        Use ``apps.organizations.decorators.PermissionRequiredMixin`` for
        class-based views or ``core.permissions.ensure_request_permission``
        for inline checks in function-based views.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            raise ImproperlyConfigured(
                "org_permission_required has been removed. " + _FBV_REMOVED_HINT
            )

        return wrapper

    return decorator


def org_level_required(min_level):
    """
    .. removed::
        This decorator has been removed. It relied on role-level checks that
        bypass the organization RBAC model.

        Use ``apps.organizations.decorators.LevelRequiredMixin`` for
        class-based views.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            raise ImproperlyConfigured(
                "org_level_required has been removed. " + _FBV_REMOVED_HINT
            )

        return wrapper

    return decorator


def org_role_required(role_names):
    """
    .. removed::
        This decorator has been removed. Role-name matching is fragile and ties
        code to role implementation details.

        Use ``apps.organizations.decorators.PermissionRequiredMixin`` with an
        RBAC permission string that captures the required capability.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            raise ImproperlyConfigured(
                "org_role_required has been removed. " + _FBV_REMOVED_HINT
            )

        return wrapper

    return decorator


# Class-based view mixins


class OrganizationRequiredMixin:
    """
    Mixin to require an active organization for class-based views.
    """

    def _check_organization_access(self, request):
        """
        Perform authentication and organization checks.

        Returns an early response (redirect or forbidden) if a check fails,
        or ``None`` when all checks pass.  Subclasses should call this helper
        and return its result immediately if it is not ``None`` rather than
        calling ``super().dispatch()``, which would execute the view body a
        second time.
        """
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not hasattr(request, "organization") or request.organization is None:
            return redirect("organizations:select")

        return None

    def dispatch(self, request, *args, **kwargs):
        response = self._check_organization_access(request)
        if response is not None:
            return response

        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(self.request.get_full_path())


class PermissionRequiredMixin(OrganizationRequiredMixin):
    """
    Mixin to check for a specific permission in class-based views.
    """

    permission_required = None

    def dispatch(self, request, *args, **kwargs):
        # Check authentication and organization access first.
        response = self._check_organization_access(request)
        if response is not None:
            return response

        # Then check the required permission.
        if self.permission_required:
            if not has_permission(request.org_permissions, self.permission_required):
                return HttpResponseForbidden(
                    pgettext("organizations.decorators.error", "missing_permission").format(
                        permission=self.permission_required
                    )
                )

        # Bypass OrganizationRequiredMixin.dispatch() — its checks are already
        # done above — and call the next class in MRO exactly once.
        return super(OrganizationRequiredMixin, self).dispatch(request, *args, **kwargs)


class LevelRequiredMixin(OrganizationRequiredMixin):
    """
    Mixin to check for minimum role level in class-based views.
    """

    min_level = 50

    def dispatch(self, request, *args, **kwargs):
        # Check authentication and organization access first.
        response = self._check_organization_access(request)
        if response is not None:
            return response

        # Then check the role level.
        max_level = 0
        if request.org_memberships:
            max_level = max([m.role.level for m in request.org_memberships], default=0)

        if max_level < self.min_level:
            return HttpResponseForbidden(
                pgettext("organizations.decorators.error", "insufficient_role_level_simple").format(
                    required=self.min_level
                )
            )

        # Bypass OrganizationRequiredMixin.dispatch() — its checks are already
        # done above — and call the next class in MRO exactly once.
        return super(OrganizationRequiredMixin, self).dispatch(request, *args, **kwargs)
