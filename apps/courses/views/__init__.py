"""
courses/views/__init__.py — FASAD.

F3 rol-skeleti (2026-07-02, AGENTS §6): fayllar views/{student,teacher,shared}/
qovluqlarına köçürülüb; membership.py rol üzrə bölünüb (StudentCoursesView →
student/). Mövcud import səthi dəyişmir.
"""

from .shared import CourseDashboardView
from .student import StudentCoursesView
from .teacher import (
    AddMembersBulkView,
    AddMemberView,
    AddResourceView,
    AddTopicView,
    AvailableStudentsView,
    CourseMembersView,
    CreateCourseView,
    DeleteCourseView,
    DeleteGroupFromCourseView,
    DeleteMemberView,
    DeleteResourceView,
    DeleteTopicView,
    EditCourseView,
    EditTopicView,
    MyCoursesListView,
    link_exam_to_course,
    unlink_exam_from_course,
    update_course_status,
)

__all__ = [
    "CreateCourseView",
    "EditCourseView",
    "DeleteCourseView",
    "MyCoursesListView",
    "update_course_status",
    "CourseDashboardView",
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
    "StudentCoursesView",
    "link_exam_to_course",
    "unlink_exam_from_course",
]
