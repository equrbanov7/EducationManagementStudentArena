"""
Core permission utilities for EMS Arena project.
Helper functions and decorators for permission checks.
"""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def is_teacher(user):
    """
    Check if user is a teacher.
    """
    return hasattr(user, "role") and user.role == "teacher"


def is_student(user):
    """
    Check if user is a student.
    """
    return hasattr(user, "role") and user.role == "student"


def teacher_required(view_func):
    """
    Decorator that requires the user to be a teacher.
    """

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
    """
    Decorator that requires the user to be a student.
    """

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
