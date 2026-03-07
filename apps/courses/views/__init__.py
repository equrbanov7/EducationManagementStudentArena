"""
courses/views/__init__.py
──────────────────────────
Re-exports all views for backward compatibility with URLs.

This allows the existing urls.py to continue working with:
    from . import views
    views.CreateCourseView.as_view()
"""

# ═══════════════════════════════════════════════════════════════
# CRUD Views
# ═══════════════════════════════════════════════════════════════
from .crud import CreateCourseView, DeleteCourseView, EditCourseView, MyCoursesListView, update_course_status

# ═══════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════
from .dashboard import CourseDashboardView

# ═══════════════════════════════════════════════════════════════
# Topics
# ═══════════════════════════════════════════════════════════════
from .topics import AddTopicView, DeleteTopicView, EditTopicView

# ═══════════════════════════════════════════════════════════════
# Resources
# ═══════════════════════════════════════════════════════════════
from .resources import AddResourceView, DeleteResourceView

# ═══════════════════════════════════════════════════════════════
# Membership
# ═══════════════════════════════════════════════════════════════
from .membership import (
    AddMemberView,
    AddMembersBulkView,
    AvailableStudentsView,
    CourseMembersView,
    DeleteGroupFromCourseView,
    DeleteMemberView,
    StudentCoursesView,
    link_exam_to_course,
    unlink_exam_from_course,
)

# ═══════════════════════════════════════════════════════════════
# __all__ - Explicit exports
# ═══════════════════════════════════════════════════════════════
__all__ = [
    # CRUD
    "CreateCourseView",
    "EditCourseView",
    "DeleteCourseView",
    "MyCoursesListView",
    "update_course_status",
    # Dashboard
    "CourseDashboardView",
    # Topics
    "AddTopicView",
    "EditTopicView",
    "DeleteTopicView",
    # Resources
    "AddResourceView",
    "DeleteResourceView",
    # Membership
    "CourseMembersView",
    "AvailableStudentsView",
    "AddMemberView",
    "AddMembersBulkView",
    "DeleteMemberView",
    "DeleteGroupFromCourseView",
    "StudentCoursesView",
    "link_exam_to_course",
    "unlink_exam_from_course",
]
