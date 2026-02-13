"""
Decorators for organization and permission-based access control.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import View

from .permissions import has_permission


def org_required(view_func):
    """
    Decorator to ensure user has an active organization selected.
    Redirects to organization selector if no organization is active.
    """

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, "organization") or request.organization is None:
            # Redirect to organization selector
            return redirect("organizations:select")
        return view_func(request, *args, **kwargs)

    return wrapper


def org_permission_required(permission):
    """
    Decorator to check if user has a specific permission in the active organization.

    Args:
        permission: Permission string to check (e.g., 'course.create')
    """

    def decorator(view_func):
        @wraps(view_func)
        @org_required
        def wrapper(request, *args, **kwargs):
            if not has_permission(request.org_permissions, permission):
                raise PermissionDenied(f"You do not have permission: {permission}")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def org_level_required(min_level):
    """
    Decorator to check if user has a role with at least the specified level.

    Args:
        min_level: Minimum role level required (1-100)
    """

    def decorator(view_func):
        @wraps(view_func)
        @org_required
        def wrapper(request, *args, **kwargs):
            # Get highest level from user's memberships
            max_level = 0
            if request.org_memberships:
                max_level = max(
                    [m.role.level for m in request.org_memberships], default=0
                )

            if max_level < min_level:
                raise PermissionDenied(
                    f"Insufficient role level. Required: {min_level}, Your level: {max_level}"
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def org_role_required(role_names):
    """
    Decorator to check if user has one of the specified roles.

    Args:
        role_names: List of role names or a single role name string
    """
    if isinstance(role_names, str):
        role_names = [role_names]

    def decorator(view_func):
        @wraps(view_func)
        @org_required
        def wrapper(request, *args, **kwargs):
            user_roles = [m.role.name for m in request.org_memberships]

            if not any(role in user_roles for role in role_names):
                raise PermissionDenied(f"Required role: {', '.join(role_names)}")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# Class-based view mixins


class OrganizationRequiredMixin:
    """
    Mixin to require an active organization for class-based views.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not hasattr(request, "organization") or request.organization is None:
            return redirect("organizations:select")

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
        # First check organization requirement
        response = super().dispatch(request, *args, **kwargs)
        if not isinstance(response, type(None)) and response.status_code != 200:
            return response

        # Then check permission
        if self.permission_required:
            if not has_permission(request.org_permissions, self.permission_required):
                return HttpResponseForbidden(
                    f"You do not have permission: {self.permission_required}"
                )

        return super(OrganizationRequiredMixin, self).dispatch(request, *args, **kwargs)


class LevelRequiredMixin(OrganizationRequiredMixin):
    """
    Mixin to check for minimum role level in class-based views.
    """

    min_level = 50

    def dispatch(self, request, *args, **kwargs):
        # First check organization requirement
        response = super().dispatch(request, *args, **kwargs)
        if not isinstance(response, type(None)) and response.status_code != 200:
            return response

        # Then check level
        max_level = 0
        if request.org_memberships:
            max_level = max([m.role.level for m in request.org_memberships], default=0)

        if max_level < self.min_level:
            return HttpResponseForbidden(
                f"Insufficient role level. Required: {self.min_level}"
            )

        return super(OrganizationRequiredMixin, self).dispatch(request, *args, **kwargs)
