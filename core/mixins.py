"""
Core view mixins for EMS Arena project.
Reusable mixins for views that require specific permissions.
"""

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect


class TeacherRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be a teacher.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, "role") or request.user.role != "teacher":
            messages.error(request, "You must be a teacher to access this page.")
            return redirect("blog:index")
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be a student.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, "role") or request.user.role != "student":
            messages.error(request, "You must be a student to access this page.")
            return redirect("blog:index")
        return super().dispatch(request, *args, **kwargs)


class OwnerRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be the owner of the object.
    """

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.user != request.user and not request.user.is_staff:
            messages.error(request, "You don't have permission to access this page.")
            return redirect("blog:index")
        return super().dispatch(request, *args, **kwargs)
