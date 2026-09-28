"""Müəllim/owner səthi (F3 rol-skeleti, 2026-07-02)."""

from .ai import CourseAIApplyView, CourseAIPlanView
from .crud import CreateCourseView, DeleteCourseView, EditCourseView, MyCoursesListView, update_course_status
from .groups import AddMembersBulkView, AvailableGroupsView, DeleteGroupFromCourseView
from .membership import (
    AddMemberView,
    AvailableStudentsView,
    CourseMembersView,
    DeleteMemberView,
    link_exam_to_course,
    unlink_exam_from_course,
)
from .resources import AddResourceView, DeleteResourceView
from .topics import AddTopicView, DeleteTopicView, EditTopicView

__all__ = [
    "CourseAIPlanView",
    "CourseAIApplyView",
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
    "AvailableGroupsView",
    "AddMemberView",
    "AddMembersBulkView",
    "DeleteMemberView",
    "DeleteGroupFromCourseView",
    "link_exam_to_course",
    "unlink_exam_from_course",
]
