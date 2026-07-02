"""Müəllim/owner səthi (F3 rol-skeleti, 2026-07-02)."""

from .crud import CreateCourseView, DeleteCourseView, EditCourseView, MyCoursesListView, update_course_status
from .membership import (
    AddMembersBulkView,
    AddMemberView,
    AvailableStudentsView,
    CourseMembersView,
    DeleteGroupFromCourseView,
    DeleteMemberView,
    link_exam_to_course,
    unlink_exam_from_course,
)
from .resources import AddResourceView, DeleteResourceView
from .topics import AddTopicView, DeleteTopicView, EditTopicView

__all__ = [
    "CreateCourseView",
    "EditCourseView",
    "DeleteCourseView",
    "MyCoursesListView",
    "update_course_status",
    "AddTopicView",
    "EditTopicView",
    "DeleteTopicView",
    "AddResourceView",
    "DeleteResourceView",
    "CourseMembersView",
    "AvailableStudentsView",
    "AddMemberView",
    "AddMembersBulkView",
    "DeleteMemberView",
    "DeleteGroupFromCourseView",
    "link_exam_to_course",
    "unlink_exam_from_course",
]
