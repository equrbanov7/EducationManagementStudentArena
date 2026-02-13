"""
Core view mixins for EMS Arena project.
Reusable mixins for views that require specific permissions.
"""

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect


class TeacherRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be a teacher or higher role.
    Uses group-based role system with is_teacher_or_above property.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request.user, "is_teacher_or_above", False):
            messages.error(request, "You must be a teacher to access this page.")
            return redirect("blog:index")
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(AccessMixin):
    """
    Mixin that requires the user to be a student.
    Uses group-based role system with is_student property.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request.user, "is_student", False):
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
